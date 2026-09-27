import { test } from 'node:test';
import assert from 'node:assert/strict';

import { captionStyle } from '../src/stage/caption.js';

test('the caption keeps the configured size as a number the frame scales', () => {
    assert.equal(captionStyle({ text_font_size: 75 })['--caption-size'], '75');
});

test('only the configured number of lines is shown, at least one', () => {
    assert.equal(captionStyle({ text_lines: 2 })['--caption-lines'], '2');
    assert.equal(captionStyle({ text_lines: 0 })['--caption-lines'], '4');
    assert.equal(captionStyle({ text_lines: null })['--caption-lines'], '4');
});

test('the caption wraps where the obs one would, never wider than the frame', () => {
    assert.equal(captionStyle({ text_line_width: 40 }).maxWidth, 'min(90vw, 40ch)');
});
