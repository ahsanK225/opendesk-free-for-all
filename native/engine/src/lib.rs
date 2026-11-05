//! Native OpenDesk engine: capture, authorized sessions, media and delivery.
// The Lite voice stub owns nothing, so dropping it early is a harmless no-op.
#![cfg_attr(not(feature = "full"), allow(clippy::drop_non_drop))]
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
pub mod h264;
pub mod jpeg;
pub mod legacy;
pub mod media;
pub mod mqtt;
pub mod net;
pub mod network;
pub mod p2p;
pub mod platform;
pub mod protocol;
pub mod session;
pub mod store;
pub mod stream;
pub mod transport;
pub mod updater;
