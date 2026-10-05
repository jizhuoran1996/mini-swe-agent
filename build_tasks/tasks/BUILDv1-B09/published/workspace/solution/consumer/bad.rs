// Negative consumer: moving a value out while a borrow is live must be rejected.
fn main() {
    let s = String::from("owned");
    let r = &s;
    drop(s);
    println!("{}", r);
}
