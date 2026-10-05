//! Consumer arithmetic helpers.

/// Adds two numbers.
pub fn add(a: i32, b: i32) -> i32 {
    a + b
}

/// Multiplies through a generic iterator over integer values.
pub fn product<I>(iter: I) -> i64
where
    I: IntoIterator<Item = i32>,
{
    iter.into_iter().map(|v| v as i64).product()
}
