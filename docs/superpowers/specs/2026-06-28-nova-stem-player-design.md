# Nova Stem Player Design

## Goal

Build a full workstation-style music player that Nova can generate from chat when the user asks for a music player with stem control.

## Context

Nova currently has a narrow sandbox builder in `src/nova_sandbox_game_builder.py`. It detects Pac-Man-style and Temple Run-style game requests, writes a project under `sandbox/app_builder_projects`, and `nova_enhanced_server.py` returns the project link. A music-player request currently falls through to generic conversation behavior.

## Product Shape

The generated project is `Nova Stem Player`, a React + Vite app stored at `sandbox/app_builder_projects/Nova_Stem_Player`.

The first screen is the app itself, not a landing page:

- Left library rail for loading audio and stem files.
- Center transport and waveform workspace.
- Stem mixer for vocals, drums, bass, and other/melody.
- Right inspector for EQ, speed, pitch, loop, export, and system status.
- Bottom transport with play/pause, seek, volume, and timing.

## Audio Behavior

The browser app uses Web Audio API primitives for local playback, filtering, visualization, and gain routing. MDN documents Web Audio as a system for audio sources, effects, visualizations, and processing; `BiquadFilterNode` supports filter/EQ-style processing; `MediaElementAudioSourceNode` connects an HTML media element into an audio graph.

True source separation is not implemented inside this first local app because real-time stem separation requires a model/runtime layer. Serato's current Stems documentation describes the expected professional workflow as isolating vocals, bass, melody, and drums, and notes that this processing can require significant CPU. This app therefore supports two honest modes:

- Real stem mode: load separate audio files for vocals, drums, bass, and other/melody, then control each stem with gain, mute, solo, and meters.
- Approximation mode: load one mixed track and use frequency-zone controls labeled as simulated stem shaping.

## Nova Integration

Nova gains:

- `is_stem_music_player_request(text)`.
- `build_stem_music_player(projects_root=None)`.
- A server routing path that creates the project before generic LLM response.
- Project and preview buttons in `nova_chat_web.html`.
- Tests proving the request is detected, the React/Vite app files are generated, and the server can route a music-player request.

## Files

- `src/nova_sandbox_game_builder.py`: add the project generator and detector.
- `nova_enhanced_server.py`: add the builder route and trace metadata.
- `nova_chat_web.html`: add `Nova Stem Player` to project and preview panels.
- `tests/test_nova_sandbox_game_builder.py`: add detector and generated-project assertions.
- `tests/test_nova_enhanced_server.py`: add server routing coverage if existing test seams allow it.
- `sandbox/app_builder_projects/Nova_Stem_Player/`: generated React + Vite app.

## Verification

- Python builder tests with `py -3.11 -m pytest`.
- JavaScript package install/build/test inside `sandbox/app_builder_projects/Nova_Stem_Player`.
- Browser verification of the running app on desktop and mobile widths.
- Final push of the verified branch.

## Sources

- MDN Web Audio API: https://developer.mozilla.org/en-US/docs/Web/API/Web_Audio_API
- MDN `BiquadFilterNode`: https://developer.mozilla.org/en-US/docs/Web/API/BiquadFilterNode
- MDN `MediaElementAudioSourceNode`: https://developer.mozilla.org/en-US/docs/Web/API/MediaElementAudioSourceNode
- MDN Media Session API: https://developer.mozilla.org/en-US/docs/Web/API/Media_Session_API
- MDN `showOpenFilePicker()`: https://developer.mozilla.org/en-US/docs/Web/API/Window/showOpenFilePicker
- Serato Stems overview: https://support.serato.com/hc/en-us/articles/5700968326927-Stems-Overview
