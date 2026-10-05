// Out-of-tree consumer for the freshly installed Arrow core+IPC SDK.
// Builds a nullable table with int32/utf8/float64 columns, writes an Arrow IPC
// file through the installed SDK, re-reads it and asserts schema, row order,
// null positions and values. Fails loudly on any mismatch.
#include <arrow/api.h>
#include <arrow/io/api.h>
#include <arrow/ipc/reader.h>
#include <arrow/ipc/writer.h>

#include <iostream>
#include <string>

static int fail(const std::string& what) {
  std::cerr << "CONSUMER_FAIL: " << what << std::endl;
  return 1;
}

int main(int argc, char** argv) {
  if (argc < 2) {
    std::cerr << "usage: consumer <output.arrow>\n";
    return 2;
  }
  const std::string path = argv[1];

  arrow::Int32Builder ib;
  if (!ib.Append(1).ok() || !ib.AppendNull().ok() || !ib.Append(3).ok() ||
      !ib.Append(4).ok())
    return fail("int build");
  std::shared_ptr<arrow::Array> iarr;
  if (!ib.Finish(&iarr).ok()) return fail("int finish");

  arrow::StringBuilder sb;
  if (!sb.Append("alpha").ok() || !sb.Append("beta").ok() ||
      !sb.AppendNull().ok() || !sb.Append("delta").ok())
    return fail("str build");
  std::shared_ptr<arrow::Array> sarr;
  if (!sb.Finish(&sarr).ok()) return fail("str finish");

  arrow::DoubleBuilder db;
  if (!db.Append(1.5).ok() || !db.Append(2.5).ok() || !db.Append(3.5).ok() ||
      !db.AppendNull().ok())
    return fail("dbl build");
  std::shared_ptr<arrow::Array> darr;
  if (!db.Finish(&darr).ok()) return fail("dbl finish");

  auto schema = arrow::schema({arrow::field("i", arrow::int32()),
                               arrow::field("s", arrow::utf8()),
                               arrow::field("d", arrow::float64())});
  auto batch = arrow::RecordBatch::Make(schema, 4, {iarr, sarr, darr});

  {
    auto out_res = arrow::io::FileOutputStream::Open(path);
    if (!out_res.ok()) return fail(out_res.status().ToString());
    auto out = *out_res;
    auto w_res = arrow::ipc::MakeFileWriter(out.get(), schema);
    if (!w_res.ok()) return fail(w_res.status().ToString());
    auto writer = *w_res;
    if (!writer->WriteRecordBatch(*batch).ok()) return fail("write batch");
    if (!writer->Close().ok()) return fail("writer close");
    if (!out->Close().ok()) return fail("stream close");
  }

  std::shared_ptr<arrow::ipc::RecordBatchFileReader> reader;
  {
    auto in_res = arrow::io::ReadableFile::Open(path);
    if (!in_res.ok()) return fail(in_res.status().ToString());
    auto r_res = arrow::ipc::RecordBatchFileReader::Open(*in_res);
    if (!r_res.ok()) return fail(r_res.status().ToString());
    reader = *r_res;
  }

  if (reader->num_record_batches() != 1) return fail("batch count");
  auto rb_res = reader->ReadRecordBatch(0);
  if (!rb_res.ok()) return fail(rb_res.status().ToString());
  auto rb = *rb_res;

  if (rb->num_rows() != 4 || rb->num_columns() != 3) return fail("shape");
  if (!rb->schema()->Equals(*schema)) return fail("schema");

  auto i = std::static_pointer_cast<arrow::Int32Array>(rb->column(0));
  auto s = std::static_pointer_cast<arrow::StringArray>(rb->column(1));
  auto d = std::static_pointer_cast<arrow::DoubleArray>(rb->column(2));

  if (i->Value(0) != 1 || !i->IsNull(1) || i->Value(2) != 3 || i->Value(3) != 4)
    return fail("int values/nulls");
  if (s->GetString(0) != "alpha" || s->GetString(1) != "beta" || !s->IsNull(2) ||
      s->GetString(3) != "delta")
    return fail("str values/nulls");
  if (d->Value(0) != 1.5 || d->Value(1) != 2.5 || d->Value(2) != 3.5 || !d->IsNull(3))
    return fail("dbl values/nulls");

  std::cout << "CONSUMER_OK rows=4 columns=3 nulls=i1,s1,d1" << std::endl;
  return 0;
}
