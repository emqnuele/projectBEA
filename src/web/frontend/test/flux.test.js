/**
 * Every event category the engine publishes has a badge of its own.
 *
 * `fluxOf` falls back to SYS for anything it does not know, which is the right
 * default and a terrible way to find out a category was forgotten: tool calls
 * were rendered as system events for as long as the category existed, and the
 * Activity page — which matches on the category rather than falling back —
 * hid them entirely.
 */

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { describe, it } from 'node:test';

import { FLUX, fluxOf } from '../src/lib/cn.js';

// the source of truth: src/core/events.py
const CATEGORIES = ['system', 'input', 'output', 'thought', 'skill', 'tool', 'error'];

const activity = readFileSync(new URL('../src/pages/ActivityPage.jsx', import.meta.url), 'utf8');
const css = readFileSync(new URL('../src/index.css', import.meta.url), 'utf8');

describe('the event flux', () => {
    it('has a badge for every category the engine publishes', () => {
        for (const category of CATEGORIES) {
            assert.ok(FLUX[category], `no badge for '${category}'`);
            assert.equal(fluxOf({ category }).label, FLUX[category].label);
        }
    });

    it('defines every colour it names', () => {
        for (const [category, flux] of Object.entries(FLUX)) {
            const token = flux.color.replace(/var\(|\)/g, '');
            assert.ok(css.includes(`${token}:`), `${category} uses undefined ${token}`);
        }
    });

    it('lets the activity page filter every category', () => {
        for (const category of CATEGORIES) {
            if (category === 'system') continue; // cost and attention split it up
            assert.ok(
                activity.includes(`e.category === '${category}'`),
                `the activity page has no filter matching '${category}'`,
            );
        }
    });
});
