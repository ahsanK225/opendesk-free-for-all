use anyhow::Result;
use serde_json::{Value, json};
use std::time::{Duration, Instant};
pub fn timing(mut values: Vec<f64>) -> Value {
    if values.is_empty() {
        return json!({"samples":0});
    }
    values.sort_by(f64::total_cmp);
    json!({"samples":values.len(),"mean_ms":values.iter().sum::<f64>()/values.len() as f64,"p50_ms":values[values.len()/2],"p95_ms":values[((values.len()-1) as f64*0.95).round() as usize],"max_ms":values[values.len()-1]})
}
pub fn report(capture: bool) -> Result<Value> {
    let mut report = json!({"version":env!("CARGO_PKG_VERSION"),"scope":"Native codec stage timings; excludes network and GPU presentation. These are not delivered internet FPS.","codec":crate::media::benchmark()?});
    report["jpeg_backend"] = json!(crate::jpeg::name());
    if capture {
        let mut capturer = crate::capture::Capture::new()?;
        let mut samples = Vec::new();
        let mut empty = 0;
        let mut dimensions = (0, 0);
        for _ in 0..60 {
            let start = Instant::now();
            if let Some((width, height, _)) = capturer.grab()? {
                dimensions = (width, height);
                samples.push(start.elapsed().as_secs_f64() * 1000.0);
            } else {
                empty += 1;
            }
            std::thread::sleep(Duration::from_millis(16));
        }
        report["capture"] = json!({"backend":capturer.backend,"dimensions":[dimensions.0,dimensions.1],"changed_frame_capture":timing(samples),"idle_polls_excluded":empty});
    }
    Ok(report)
}
