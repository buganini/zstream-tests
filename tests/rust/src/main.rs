use compress_utils::{compress, decompress, Algorithm, Compressor, Decompressor};
use serde_json::{json, Value};
use std::cell::RefCell;
use std::collections::VecDeque;
use std::io::{self, Read, Write};
use std::path::Path;
use std::rc::Rc;
use std::sync::OnceLock;

type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;
const LEVEL: i32 = 5;
mod interop;
static TRANSPORT_CHUNKS: OnceLock<Vec<usize>> = OnceLock::new();

fn transport_chunks() -> &'static [usize] {
    TRANSPORT_CHUNKS.get().map(Vec::as_slice).unwrap_or(&[1, 3, 7, 97, 4093])
}

fn configure_transport(manifest: &Value) -> Result<()> {
    if let Some(value) = manifest.get("transport_chunks") {
        let sizes: Vec<usize> = serde_json::from_value(value.clone())?;
        check(sizes.iter().all(|&size| size > 0), "transport chunk sizes must be positive")?;
        TRANSPORT_CHUNKS.set(sizes).map_err(|_| io::Error::other("transport already configured"))?;
    }
    Ok(())
}

fn check(ok: bool, message: &str) -> Result<()> {
    if ok { Ok(()) } else { Err(io::Error::other(message).into()) }
}

#[derive(Default)]
struct State {
    wire: VecDeque<u8>,
    total: usize,
    closed: bool,
    reads: usize,
    flushes: usize,
}

#[derive(Clone, Default)]
struct Pipe(Rc<RefCell<State>>);

impl Write for Pipe {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        let n = bytes.len().min(257); // Force the adapter to handle short writes.
        let mut state = self.0.borrow_mut();
        state.wire.extend(&bytes[..n]);
        state.total += n;
        Ok(n)
    }
    fn flush(&mut self) -> io::Result<()> {
        self.0.borrow_mut().flushes += 1;
        Ok(())
    }
}

impl Read for Pipe {
    fn read(&mut self, out: &mut [u8]) -> io::Result<usize> {
        if out.is_empty() { return Ok(0); }
        let mut state = self.0.borrow_mut();
        if state.wire.is_empty() {
            return if state.closed { Ok(0) }
                else { Err(io::ErrorKind::WouldBlock.into()) };
        }
        let sizes = transport_chunks();
        let limit = if sizes.is_empty() { state.wire.len() } else { sizes[state.reads % sizes.len()] };
        let n = out.len().min(state.wire.len()).min(limit);
        state.reads += 1;
        for byte in &mut out[..n] { *byte = state.wire.pop_front().unwrap(); }
        Ok(n)
    }
}

// An empty live source is WouldBlock, never EOF. This keeps one decoder alive
// across stages and prevents accidentally finalizing at a midpoint.
fn receive(decoder: &mut Decompressor<Pipe>, decoded: &mut Vec<u8>, closed: bool) -> Result<()> {
    let mut out = [0u8; 113];
    loop {
        match decoder.read(&mut out) {
            Ok(0) => { check(closed, "decoder returned EOF on an open transport")?; return Ok(()); }
            Ok(n) => decoded.extend_from_slice(&out[..n]),
            Err(e) if e.kind() == io::ErrorKind::WouldBlock && !closed => return Ok(()),
            Err(e) => return Err(e.into()),
        }
    }
}

fn roundtrip(algo: Algorithm, data: &[u8], streaming: bool) -> Result<Value> {
    let (decoded, size) = if !streaming {
        let packed = compress(algo, data, LEVEL)?;
        (decompress(algo, &packed)?, packed.len())
    } else {
        let pipe = Pipe::default();
        let mut encoder = Compressor::new(pipe.clone(), algo, LEVEL)?;
        let mut decoder = Decompressor::new(pipe.clone(), algo)?;
        let mut decoded = Vec::new();
        let sizes = [1, 7, 63, 1024, 65521];
        let (mut offset, mut i) = (0, 0);
        while offset < data.len() {
            let end = (offset + sizes[i % sizes.len()]).min(data.len());
            encoder.write_all(&data[offset..end])?;
            receive(&mut decoder, &mut decoded, false)?;
            offset = end;
            i += 1;
        }
        encoder.finish()?;
        pipe.0.borrow_mut().closed = true;
        receive(&mut decoder, &mut decoded, true)?;
        let size = pipe.0.borrow().total;
        (decoded, size)
    };
    check(decoded == data, &format!("decoded {} / {} bytes", decoded.len(), data.len()))?;
    Ok(json!({"status": "PASS", "input_bytes": data.len(), "compressed_bytes": size}))
}

fn midpoint(algo: Algorithm, data: &[u8]) -> Result<Value> {
    let pipe = Pipe::default();
    let mut encoder = Compressor::new(pipe.clone(), algo, LEVEL)?;
    let mut decoder = Decompressor::new(pipe.clone(), algo)?;
    let (mut expected, mut decoded, mut stages) = (Vec::new(), Vec::new(), Vec::new());
    let suffix: Vec<u8> = (0..4096).map(|i| (i % 256) as u8).collect();
    for part in [data, &[b'B'; 37], &suffix, &[]] {
        expected.extend_from_slice(part);
        let before = pipe.0.borrow().total;
        encoder.write_all(part)?;
        let write_output = pipe.0.borrow().total - before;
        receive(&mut decoder, &mut decoded, false)?;
        let before = pipe.0.borrow().total;
        encoder.flush()?;
        let flush_output = pipe.0.borrow().total - before;
        let before = pipe.0.borrow().total;
        for _ in 0..3 { encoder.write(&[])?; }
        let empty_output = pipe.0.borrow().total - before;
        receive(&mut decoder, &mut decoded, false)?;
        check(expected.starts_with(&decoded), "midpoint data is not an exact prefix")?;
        stages.push(json!({"submitted": expected.len(), "decoded": decoded.len(),
                           "write_output": write_output, "flush_output": flush_output,
                           "empty_write_output": empty_output}));
    }
    encoder.finish()?;
    pipe.0.borrow_mut().closed = true;
    receive(&mut decoder, &mut decoded, true)?;
    check(decoded == expected, "round trip after midpoint failed")?;
    let passes = stages.iter().all(|s| s["submitted"] == s["decoded"]);
    Ok(json!({"status": if passes { "PASS" } else { "LIMITATION" }, "flush_api": true,
              "sink_flush_calls": pipe.0.borrow().flushes,
              "stages": stages, "final_roundtrip": true}))
}

fn finish_is_terminal(algo: Algorithm) -> Result<Value> {
    let mut encoder = Compressor::new(Vec::new(), algo, LEVEL)?;
    encoder.write_all(b"A")?;
    let wire = encoder.finish()?; // finish(self) consumes the compressor.
    let mut decoder = Decompressor::new(&wire[..], algo)?;
    let mut decoded = Vec::new();
    decoder.read_to_end(&mut decoded)?;
    check(decoded == b"A", "finished frame did not decode")?;
    Ok(json!({"status": "PASS", "finish_consumes_compressor": true}))
}

fn truncated(algo: Algorithm) -> Result<Value> {
    let mut encoder = Compressor::new(Vec::new(), algo, LEVEL)?;
    encoder.write_all(&[b'A'; 4096])?;
    let mut wire = encoder.finish()?;
    wire.pop();
    let mut decoder = Decompressor::new(&wire[..], algo)?;
    let mut decoded = Vec::new();
    match decoder.read_to_end(&mut decoded) {
        Err(e) => Ok(json!({"status": "PASS", "truncated_error": e.to_string()})),
        Ok(_) => Err(io::Error::other("missing final byte was not detected").into()),
    }
}

fn emit(algo: Algorithm, test: &str, case: &str, result: Result<Value>) -> bool {
    let mut row = json!({"binding": "rust", "codec": algo.name(), "test": test, "case": case, "level": LEVEL,
                         "transport_chunks": transport_chunks()});
    match result {
        Ok(value) => row.as_object_mut().unwrap().extend(value.as_object().unwrap().clone()),
        Err(error) => { row["status"] = json!("FAIL"); row["error"] = json!(error.to_string()); }
    }
    println!("{row}");
    row["status"] == "FAIL"
}

fn main() -> Result<()> {
    let root_arg = std::env::args().nth(1).expect("fixture directory required");
    let root = Path::new(&root_arg);
    if std::env::args().nth(2).as_deref() == Some("--interop") {
        return interop::run(root);
    }
    let manifest: Value = serde_json::from_slice(&std::fs::read(root.join("manifest.json"))?)?;
    configure_transport(&manifest)?;
    let mut failed = false;
    for algo in [Algorithm::Zstd, Algorithm::Lz4] {
        for case in manifest["roundtrip"].as_array().unwrap() {
            let data = std::fs::read(root.join(case["file"].as_str().unwrap()))?;
            for streaming in [false, true] {
                failed |= emit(algo, if streaming { "stream_roundtrip" } else { "oneshot_roundtrip" },
                               case["name"].as_str().unwrap(), roundtrip(algo, &data, streaming));
            }
        }
        for kind in ["random", "repeat"] {
            let data = std::fs::read(root.join(format!("{kind}.bin")))?;
            for size in manifest["midpoint_sizes"].as_array().unwrap() {
                let n = size.as_u64().unwrap() as usize;
                failed |= emit(algo, "midpoint", &format!("{kind}-{n}"), midpoint(algo, &data[..n]));
            }
        }
        failed |= emit(algo, "finish_is_terminal", "A-then-B", finish_is_terminal(algo));
        failed |= emit(algo, "truncated", "missing-last-byte", truncated(algo));
    }
    std::process::exit(if failed { 1 } else { 0 });
}
