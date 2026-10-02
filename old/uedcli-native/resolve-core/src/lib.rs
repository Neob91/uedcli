/// A build failure carrying the offending value; `lib.rs` maps this to a Python exception.
#[derive(Debug, Clone)]
pub struct BuildError(pub String);

impl std::fmt::Display for BuildError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.0)
    }
}

impl std::error::Error for BuildError {}

pub type BResult<T> = Result<T, BuildError>;

pub mod package_read;
pub mod resolve;

pub use resolve::ResolutionContext;
