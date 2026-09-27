/**
 * The output device, chosen by name. Pure, so node can test it.
 *
 * A position in the device list moves whenever a monitor or a headset is
 * plugged in, so the choice is stored as the device's name, and an empty name
 * follows whatever output the system uses.
 */

// above this the room hears her noticeably late, which is worth saying next to the choice
export const SLOW_OUTPUT_MS = 100;

/** One entry per name: Windows lists the same device once per audio api. */
export function deviceChoices(devices = []) {
    const seen = new Map();
    for (const device of devices) {
        const known = seen.get(device.name);
        if (!known || (device.default && !known.default)) seen.set(device.name, device);
    }
    return [...seen.values()];
}

/** What the picker shows as chosen: the stored name, the name behind an old position, or the system default. */
export function chosenDevice(config = {}, devices = []) {
    if (config.audio_device) return config.audio_device;
    const legacy = config.audio_device_id;
    if (Number.isInteger(legacy)) {
        const found = devices.find((device) => device.id === legacy);
        if (found) return found.name;
    }
    return '';
}

/** The device a choice lands on today, or null when it is not plugged in. */
export function deviceFor(choice, devices = []) {
    if (!choice) return devices.find((device) => device.default) || null;
    return devices.find((device) => device.name === choice) || null;
}

/** A sentence about how late the room hears her on this output, or null when it is quick. */
export function latencyNote(device) {
    if (!device || !(device.latency_ms > SLOW_OUTPUT_MS)) return null;
    return `About ${device.latency_ms} ms from her voice to the speaker, as bluetooth usually is. `
        + 'Her mouth and face wait for it; for a stream, a wired output or a virtual cable is quicker.';
}
