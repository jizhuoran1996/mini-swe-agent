// Out-of-tree static consumer for the RocksDB SDK built by BUILDv1-D04.
// Compiled only against <INSTALL_ROOT>/include and <INSTALL_ROOT>/lib/librocksdb.a.
#include <rocksdb/db.h>
#include <rocksdb/options.h>
#include <rocksdb/write_batch.h>

#include <cstdio>
#include <iostream>
#include <memory>
#include <string>

namespace {

const int kNumKeys = 100;
const int kDeletedAtWrite = 50;

std::string Key(int i) {
  char buf[32];
  std::snprintf(buf, sizeof(buf), "key-%05d", i);
  return std::string(buf);
}

std::string Value(int i) { return "value-" + std::to_string(i); }

int Fail(const std::string& message) {
  std::cerr << "CONSUMER_FAIL: " << message << std::endl;
  return 1;
}

int Ok(const std::string& message) {
  std::cout << "CONSUMER_OK: " << message << std::endl;
  return 0;
}

}  // namespace

int main(int argc, char** argv) {
  if (argc < 3) {
    std::cerr << "usage: rocksdb_consumer <write|verify|delete|final> <dbdir>" << std::endl;
    return 2;
  }
  const std::string mode = argv[1];
  const std::string path = argv[2];

  rocksdb::Options options;
  options.create_if_missing = (mode == "write");

  rocksdb::DB* raw = nullptr;
  rocksdb::Status status = rocksdb::DB::Open(options, path, &raw);
  if (!status.ok()) return Fail("open: " + status.ToString());
  std::unique_ptr<rocksdb::DB> db(raw);

  if (mode == "write") {
    rocksdb::WriteBatch batch;
    for (int i = 0; i < kNumKeys; ++i) batch.Put(Key(i), Value(i));
    batch.Delete(Key(kDeletedAtWrite));
    status = db->Write(rocksdb::WriteOptions(), &batch);
    if (!status.ok()) return Fail("write batch: " + status.ToString());
    std::string value;
    status = db->Get(rocksdb::ReadOptions(), Key(0), &value);
    if (!status.ok() || value != Value(0)) return Fail("point read after batch write");
    return Ok("wrote a 100-key WriteBatch and deleted one key");
  }

  if (mode == "verify") {
    int count = 0;
    std::unique_ptr<rocksdb::Iterator> it(db->NewIterator(rocksdb::ReadOptions()));
    for (it->SeekToFirst(); it->Valid(); it->Next()) ++count;
    if (!it->status().ok()) return Fail("iteration: " + it->status().ToString());
    if (count != kNumKeys - 1) {
      return Fail("expected 99 keys after reopen, found " + std::to_string(count));
    }
    for (int i = 0; i < kNumKeys; ++i) {
      std::string value;
      const rocksdb::Status got = db->Get(rocksdb::ReadOptions(), Key(i), &value);
      if (i == kDeletedAtWrite) {
        if (!got.IsNotFound()) return Fail("deleted key visible after reopen: " + Key(i));
      } else if (!got.ok() || value != Value(i)) {
        return Fail("value mismatch after reopen at " + Key(i));
      }
    }
    return Ok("new process reopened the db: 99 keys, deleted key absent");
  }

  if (mode == "delete") {
    status = db->Delete(rocksdb::WriteOptions(), Key(0));
    if (!status.ok()) return Fail("delete: " + status.ToString());
    std::string value;
    status = db->Get(rocksdb::ReadOptions(), Key(0), &value);
    if (!status.IsNotFound()) return Fail("key-00000 still visible after delete");
    return Ok("deleted key-00000 in a fresh process");
  }

  if (mode == "final") {
    std::string value;
    status = db->Get(rocksdb::ReadOptions(), Key(0), &value);
    if (!status.IsNotFound()) return Fail("key-00000 reappeared after reopen");
    status = db->Get(rocksdb::ReadOptions(), Key(1), &value);
    if (!status.ok() || value != Value(1)) return Fail("key-00001 not durable across reopen");
    int count = 0;
    std::unique_ptr<rocksdb::Iterator> it(db->NewIterator(rocksdb::ReadOptions()));
    for (it->SeekToFirst(); it->Valid(); it->Next()) ++count;
    if (!it->status().ok()) return Fail("final iteration: " + it->status().ToString());
    if (count != kNumKeys - 2) {
      return Fail("expected 98 keys at the end, found " + std::to_string(count));
    }
    return Ok("final reopen: 98 keys, both deletions durable");
  }

  return Fail("unknown mode: " + mode);
}
