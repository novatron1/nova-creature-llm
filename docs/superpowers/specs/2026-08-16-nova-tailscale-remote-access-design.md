# Nova PC and Phone Remote Access Design

**Date:** 2026-08-16  
**Status:** Approved for implementation

## Goal

Finish Nova as a reliable Windows-hosted application that works locally on the PC and remotely from a paired phone whenever the PC is powered on and connected to the internet. The phone connection must have a stable private HTTPS address, require no user-owned domain, and never expose Nova, Ollama, or the computer directly to the public internet.

## Success Criteria

- Nova starts reliably on Windows through a clear one-click launcher.
- The desktop browser can use Nova locally at `http://127.0.0.1:3000`.
- Tailscale Serve publishes Nova at a stable private HTTPS address inside the user's tailnet.
- A phone signed into the same tailnet can open Nova from outside the PC's local Wi-Fi network.
- The phone must complete Nova's existing secure pairing before it can use protected functionality.
- After initial setup, the phone can install Nova as a home-screen PWA and continue using the same origin across PC and Nova restarts.
- Unpaired, revoked, or out-of-tailnet clients cannot use Nova.
- Nova never opens a router port, exposes Ollama, or silently falls back to a public tunnel.
- Startup, connection, authentication, and offline failures produce clear recovery instructions.

## Chosen Approach

Use Tailscale Serve as a private HTTPS reverse proxy in front of Nova's loopback-only HTTP server.

This approach was selected because it provides a stable address without requiring a user-owned domain. Tailscale supplies the private device network and HTTPS endpoint, while Nova retains responsibility for application-level pairing, device scopes, revocation, memory policy, and tool permissions.

Cloudflare Quick Tunnels are not the primary path because their hostnames change and they are intended for temporary use. A named Cloudflare Tunnel remains a possible future extension for a user who intentionally configures a Cloudflare account and domain.

## Architecture

```text
Phone browser / installed PWA
        |
        | private encrypted tailnet connection
        v
Tailscale Serve HTTPS endpoint
        |
        | trusted loopback proxy connection
        v
Nova server on 127.0.0.1:3000
        |
        +-- Nova device pairing and scoped bearer token
        +-- Nova cognitive core and memory
        +-- local Ollama/model providers
        +-- permission-gated tools
```

Nova continues binding to loopback. Tailscale Serve terminates HTTPS and forwards requests to `http://127.0.0.1:3000`. The remote endpoint is available only to authenticated devices allowed by the same Tailscale network. Nova then applies its own independent paired-device authentication.

Ollama, ComfyUI, filesystem tools, shell tools, and other internal services remain behind Nova and are never directly published.

## Components

### Windows Anywhere Launcher

Add a clear Windows entry point for remote-capable use. It will:

1. Locate a supported Python runtime using the project's existing launcher behavior.
2. validate Nova's required Python packages and preserve the existing bounded dependency-install path;
3. detect the Tailscale executable and connection state;
4. provide precise official installation or sign-in guidance when Tailscale is unavailable;
5. start Nova on `127.0.0.1:3000` with the explicit trusted-Tailscale-proxy policy enabled;
6. configure Tailscale Serve in persistent background mode for Nova's local port;
7. read and display the effective private HTTPS URL;
8. open Nova locally and make the phone URL easy to copy; and
9. fail safely without enabling a public tunnel when any remote setup step fails.

The existing local-only Windows launcher remains available. Remote access is an explicit user choice, not a new default exposure mode.

### Trusted Proxy Boundary

Nova will distinguish the proxy connection from the original phone connection. It must not classify Tailscale-proxied phone traffic as ordinary localhost traffic.

Tailscale identity metadata will be accepted only when:

- the direct TCP peer is loopback;
- the trusted-Tailscale-proxy setting is explicitly enabled by the Anywhere launcher; and
- the expected Tailscale proxy headers are present and structurally valid.

Requests satisfying that boundary are classified as remote and must pass Nova's paired-device authentication. Generic forwarded headers are not trusted. Requests that fail validation receive the existing remote authentication failure rather than inheriting localhost privileges.

### Foundation and Companion UI

Extend Nova's existing Foundation/Settings surface rather than creating a second configuration system. The interface will show:

- Nova server health;
- Tailscale availability and Serve status;
- the active private phone URL;
- copy/open controls;
- secure pairing-code and QR-code controls;
- paired-device status and revocation controls; and
- plain-language recovery instructions when the PC, Nova, Tailscale, or the private route is unavailable.

The Companion PWA keeps its existing responsive shell, manifest, service worker, and installation behavior. The stable Tailscale HTTPS origin allows a paired browser token and installed app identity to persist across normal restarts.

### Remote Status API

Expose only the minimum content-free operational state required by the trusted local management UI. Status may include enabled/disabled state, executable availability, Serve readiness, private URL, and bounded reason codes. It must not return credentials, Tailscale authentication material, Nova bearer tokens, prompts, answers, memory contents, or private headers.

Mutating remote-access controls remain local-desktop-only. A paired phone cannot enable Tailscale Serve, alter the trusted-proxy policy, or expand its own scopes.

## Data Flow

### First-Time Setup

1. The user launches Start Nova Anywhere on Windows.
2. The launcher confirms Python and Nova readiness.
3. If Tailscale is missing or signed out, the launcher gives the user the exact official setup action and stops safely.
4. Once Tailscale is ready, the launcher starts Nova on loopback and configures persistent Tailscale Serve HTTPS forwarding.
5. The launcher obtains the stable tailnet URL and opens Nova locally.
6. The local user creates a one-time Nova pairing code or QR code.
7. The phone, signed into the same tailnet, opens the stable URL and completes pairing.
8. The paired phone stores only its Nova device credential in that private HTTPS origin and may install the PWA.

### Normal Use

1. The user opens Nova on the phone.
2. Tailscale authenticates and routes the private connection to the PC.
3. Tailscale Serve forwards the request to Nova over loopback.
4. Nova identifies the connection as remote, validates the paired-device token and scopes, and processes the request through the existing cognitive and permission layers.
5. The response returns through the same private route.

### Restart Behavior

Tailscale Serve uses its persistent background configuration. When Windows and Tailscale return, the same private HTTPS origin resumes forwarding to Nova. Nova's application launcher remains responsible for starting the local Nova process. The previously paired phone remains paired unless its Nova device credential has been revoked or cleared.

## Security and Privacy

- The remote path is private to the user's Tailscale network.
- Nova pairing remains mandatory and independent of Tailscale authentication.
- Remote requests never receive Nova's local no-auth profile.
- Paired phones receive only the existing bounded scopes required for chat, memory read, and safe tool discovery unless the desktop user explicitly grants another supported scope.
- Shell execution, arbitrary file writes, purchases, account actions, destructive tools, and privilege expansion remain unavailable to a normal phone pairing.
- The trusted proxy mode is explicit and disabled for ordinary Nova startup.
- Nova trusts Tailscale identity headers only from the loopback proxy boundary; arbitrary internet or LAN clients cannot assert them.
- The connection layer does not log prompts, responses, private memory, Nova tokens, authorization headers, or Tailscale credentials.
- No home-router port forwarding is created.
- Ollama and other backend service ports remain loopback-only and unpublished.
- Nova never silently falls back to Cloudflare Quick Tunnel, Tailscale Funnel, or another public relay.

## Failure Handling

- **Tailscale not installed:** stop before enabling remote access and show the official installation step.
- **Tailscale signed out or disconnected:** keep Nova usable locally and show how to reconnect Tailscale.
- **Serve not authorized for HTTPS:** show the exact Tailscale consent step; do not substitute insecure public HTTP.
- **Nova port already in use:** use the existing ownership-aware startup diagnosis and do not attach the private route to an unidentified process.
- **Nova fails to start:** do not report remote readiness; preserve the local error details and give a bounded recovery action.
- **Phone outside the tailnet:** show a connection-specific recovery message rather than claiming Nova is offline.
- **Phone is unpaired:** show the existing pairing-required experience.
- **Pairing code expired or reused:** reject it and instruct the desktop user to generate a fresh code.
- **Device revoked:** reject its stored token immediately and return to the pairing screen.
- **PC asleep, powered off, or offline:** the phone reports that the host PC must be awake and online.
- **Partial remote setup:** never mark the system ready until Nova health and Tailscale Serve status both pass.

## Testing and Verification

### Automated Tests

- Windows launcher detection, command construction, safe failure, and status parsing.
- Trusted proxy classification for valid loopback Tailscale Serve requests.
- Rejection of spoofed Tailscale headers from non-loopback peers.
- Rejection of remote requests when trusted proxy mode is disabled.
- Mandatory pairing for Tailscale-proxied clients.
- Successful paired chat with safe scopes.
- Revocation and expired/reused pairing-code behavior.
- Local desktop behavior remains unchanged.
- Remote status endpoints contain no secrets or private content.
- PWA manifest, service worker, stable-origin, and mobile layout regression coverage.
- Existing Foundation, gateway, desktop, companion, server, and Windows launcher tests.

### Live Verification

- Start Nova locally through the standard Windows launcher and confirm no remote access is enabled.
- Start Nova through the Anywhere launcher and confirm the local desktop app works.
- Confirm Tailscale Serve reports the expected stable HTTPS URL.
- Confirm an unpaired phone in the tailnet is denied protected access.
- Pair the phone and complete a real chat exchange outside the PC's Wi-Fi network.
- Install/open the PWA and verify responsive layout, composer, scrolling, reconnect messaging, and microphone permission behavior on a phone-sized viewport.
- Restart Nova and confirm the same URL and paired phone continue to work.
- Revoke the phone and confirm access is blocked.
- Disconnect Tailscale and stop Nova separately to verify honest recovery messages.
- Run the scoped automated suite and the repository's release/smoke checks appropriate to the changed files.

## Non-Goals

- Running Nova while the PC is powered off.
- Hosting Nova or its models in a public cloud.
- Publishing Nova through Tailscale Funnel or a public Cloudflare URL.
- Installing or configuring a user-owned domain.
- Exposing Ollama, ComfyUI, shell, filesystem, or training ports directly.
- Replacing Nova's existing identity, memory, pairing, gateway, permission, or PWA systems.
- Adding iOS or Android native applications; the installable responsive PWA remains the phone application.

## Completion Definition

The feature is complete when a Windows user can follow the first-time setup once, start Nova through the Anywhere launcher, use Nova locally, pair a phone, install the PWA, and then use that phone from a different network through the same private HTTPS address whenever the PC is on. All authentication, revocation, failure, and regression checks must pass without adding public exposure or weakening Nova's existing local security defaults.
