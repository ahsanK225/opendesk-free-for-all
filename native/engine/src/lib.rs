//! Native OpenDesk engine: capture, authorized sessions, media and delivery.
pub mod app;
pub mod audio;
pub mod capture;
pub mod client;
pub mod diagnostics;
pub mod directory;
pub mod ffi;
pub mod files;
#[cfg(test)]
mod integration_tests;
pub mod jpeg;
pub mod media;
pub mod network;
pub mod platform;
pub mod protocol;
pub mod session;
pub mod store;
pub mod stream;
pub mod transport;
pub mod updater;
