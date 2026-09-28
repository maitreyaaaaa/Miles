# Interruption benchmark scope

The benchmark in `benchmark_interruption.py` is a local software-path check. It starts the server-side TTS stream, waits briefly, triggers the interruption manager directly, and records how quickly the cancellation handler and consuming coroutine return.

It does **not** measure microphone onset detection, network cancellation time, browser playback queues, acoustic output, or the time until a listener stops hearing sound. The benchmark's `spoken_before_cut` value is derived from application state; it does not prove which audio reached the listener. Its timing values must not be presented as end-to-end barge-in latency.

The benchmark can call the configured TTS provider and use provider quota. Run it only with an explicit opt-in:

```powershell
python benchmark_interruption.py --live
```

End-to-end latency evidence would need to capture microphone onset and speaker output while exercising the real browser, network, and backend path. This repository does not currently contain that measurement.
