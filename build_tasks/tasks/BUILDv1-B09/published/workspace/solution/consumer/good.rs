// Positive consumer: generics, collections, threads, file IO.
use std::collections::HashMap;
use std::fs;
use std::sync::mpsc;
use std::thread;

fn generic_count<T>(v: &[T]) -> usize {
    v.len()
}

fn main() {
    let mut map: HashMap<String, i32> = HashMap::new();
    map.insert("a".to_string(), 1);
    map.insert("b".to_string(), 2);
    let total: i32 = map.values().sum();
    assert_eq!(total, 3);
    assert_eq!(generic_count(&[1, 2, 3]), 3);

    let (tx, rx) = mpsc::channel();
    for i in 0..4 {
        let t = tx.clone();
        thread::spawn(move || t.send(i * i).unwrap());
    }
    drop(tx);
    let mut sums: Vec<i32> = rx.iter().collect();
    sums.sort();
    assert_eq!(sums, vec![0, 1, 4, 9]);

    let path = std::env::temp_dir().join("b09_consumer.txt");
    fs::write(&path, "hello-rust\n").unwrap();
    let got = fs::read_to_string(&path).unwrap();
    assert_eq!(got, "hello-rust\n");

    println!(
        "CONSUMER_OK total={} count={} thread_sums={:?}",
        total,
        generic_count(&[1, 2, 3]),
        sums
    );
}
