/* Isolate codec buffering from wrapper behavior using the SAME vendored zstd.
 * This diagnostic is deliberately outside compress-utils' binding test counts. */
#include <zstd.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void require(int condition, const char *message) {
    if (!condition) { fprintf(stderr, "%s\n", message); exit(1); }
}

static void ok(size_t result) {
    require(!ZSTD_isError(result), ZSTD_getErrorName(result));
}

int main(int argc, char **argv) {
    require(argc == 2, "usage: native_zstd_control random.bin");
    const size_t size = 131072;
    unsigned char *data = malloc(size), *packed = malloc(size * 2), *decoded = malloc(size);
    require(data && packed && decoded, "allocation failed");
    FILE *file = fopen(argv[1], "rb");
    require(file != NULL, "cannot open random fixture");
    require(fread(data, 1, size, file) == size, "short fixture");
    fclose(file);

    ZSTD_CCtx *c = ZSTD_createCCtx();
    require(c != NULL, "create compressor failed");
    ok(ZSTD_CCtx_setParameter(c, ZSTD_c_compressionLevel, 11)); // compress-utils level 5.
    ZSTD_inBuffer in = {data, size, 0};
    ZSTD_outBuffer out = {packed, 65536, 0};
    size_t remaining = ZSTD_compressStream2(c, &out, &in, ZSTD_e_continue);
    ok(remaining);
    require(in.pos == size && out.pos == 65536 && remaining > 0, "encoder boundary not reproduced");
    size_t first = out.pos;
    ZSTD_inBuffer empty = {NULL, 0, 0};
    out = (ZSTD_outBuffer){packed + first, size * 2 - first, 0};
    ok(ZSTD_compressStream2(c, &out, &empty, ZSTD_e_continue));
    require(out.pos > 0, "native empty-input call did not drain encoder output");
    printf("{\"test\":\"native_encoder_empty_drain\",\"status\":\"PASS\",\"codec_version\":\"%s\","
           "\"input_consumed\":%zu,\"first_output\":%zu,\"empty_input_output\":%zu}\n",
           ZSTD_versionString(), in.pos, first, out.pos);
    ZSTD_freeCCtx(c);

    memset(data, 'A', size);
    c = ZSTD_createCCtx();
    require(c != NULL, "create compressor failed");
    ok(ZSTD_CCtx_setParameter(c, ZSTD_c_compressionLevel, 11));
    in = (ZSTD_inBuffer){data, size, 0};
    out = (ZSTD_outBuffer){packed, size * 2, 0};
    ok(ZSTD_compressStream2(c, &out, &in, ZSTD_e_continue));
    size_t packed_size = out.pos;
    ZSTD_DCtx *d = ZSTD_createDCtx();
    require(d != NULL, "create decoder failed");
    in = (ZSTD_inBuffer){packed, packed_size, 0};
    out = (ZSTD_outBuffer){decoded, 65536, 0};
    ok(ZSTD_decompressStream(d, &out, &in));
    require(in.pos == packed_size && out.pos == 65536, "decoder boundary not reproduced");
    first = out.pos;
    out = (ZSTD_outBuffer){decoded + first, size - first, 0};
    ok(ZSTD_decompressStream(d, &out, &empty));
    require(first + out.pos == size && memcmp(data, decoded, size) == 0, "native decoder failed empty-input drain");
    printf("{\"test\":\"native_decoder_empty_drain\",\"status\":\"PASS\",\"codec_version\":\"%s\","
           "\"compressed_input\":%zu,\"first_decoded\":%zu,\"empty_input_decoded\":%zu}\n",
           ZSTD_versionString(), packed_size, first, out.pos);
    ZSTD_freeCCtx(c);
    ZSTD_freeDCtx(d);
    free(data); free(packed); free(decoded);
    return 0;
}
