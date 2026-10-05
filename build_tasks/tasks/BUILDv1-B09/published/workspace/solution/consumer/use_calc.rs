// Cross-crate ABI consumer: links against the freshly built calc.rlib.
extern crate calc;

fn main() {
    assert_eq!(calc::add(20, 22), 42);
    assert_eq!(calc::product(vec![2, 3, 7]), 42);
    println!("USE_CALC_OK add={} product={}", calc::add(20, 22), calc::product(vec![2, 3, 7]));
}
