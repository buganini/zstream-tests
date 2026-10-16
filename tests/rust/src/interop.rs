//! Replay Python zstandard sender checkpoints through the Rust receiver.
use super::{check, receive, Algorithm, Decompressor, Pipe, Result};
use serde_json::{json, Value};
use std::path::Path;

fn probe(root: &Path, case: &Value) -> Result<Value> {
    let pipe = Pipe::default();
    let mut decoder = Decompressor::new(pipe.clone(), Algorithm::Zstd)?;
    let expected = std::fs::read(root.join(case["expected"]["file"].as_str().unwrap()))?;
    let mut decoded = Vec::new();
    let mut stages = Vec::new();
    for stage in case["stages"].as_array().unwrap() {
        let wire = std::fs::read(root.join(stage["file"].as_str().unwrap()))?;
        {
            let mut state = pipe.0.borrow_mut();
            state.wire.extend(&wire);
            state.reads = 0; // Match the per-checkpoint transport chunk sequence.
        }
        receive(&mut decoder, &mut decoded, false)?;
        let submitted = stage["submitted"].as_u64().unwrap() as usize;
        check(expected.starts_with(&decoded) && decoded.len() <= submitted, "invalid decoded prefix")?;
        stages.push(json!({"submitted": submitted, "decoded": decoded.len(),
                           "wire_bytes": wire.len(), "complete": decoded.len() == submitted}));
    }
    let tail = std::fs::read(root.join(case["tail"]["file"].as_str().unwrap()))?;
    {
        let mut state = pipe.0.borrow_mut();
        state.wire.extend(&tail);
        state.reads = 0;
        state.closed = true;
    }
    receive(&mut decoder, &mut decoded, true)?;
    check(decoded == expected, "final round trip mismatch")?;
    let passed = stages.iter().all(|s| s["complete"] == true);
    Ok(json!({"status": if passed { "PASS" } else { "LIMITATION" }, "stages": stages,
              "final_roundtrip": true, "final_bytes": decoded.len()}))
}

pub fn run(root: &Path) -> Result<()> {
    let manifest: Value = serde_json::from_slice(&std::fs::read(root.join("manifest.json"))?)?;
    let mut failed = false;
    for case in manifest["cases"].as_array().unwrap() {
        let mut row = json!({"binding": "interop_rust", "test": "sender_flush", "codec": "zstd",
                             "sender": "python_zstandard", "receiver": "compress_utils_rust",
                             "case": case["name"], "sender_api": case["sender_api"],
                             "native_level": manifest["native_level"]});
        match probe(root, case) {
            Ok(value) => row.as_object_mut().unwrap().extend(value.as_object().unwrap().clone()),
            Err(error) => {
                row["status"] = json!("FAIL");
                row["error"] = json!(error.to_string());
                failed = true;
            }
        }
        println!("{row}");
    }
    std::process::exit(if failed { 1 } else { 0 });
}
