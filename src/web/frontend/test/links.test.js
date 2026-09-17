/**
 * The links that advertise the project.
 *
 * They are in three components' chrome and in two installers; a typo in one of
 * them is a dead link nobody reports. This only asserts what a machine can:
 * that every one is an absolute https url, and that the docs live under the
 * site rather than beside it.
 */

import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { AUTHOR, LINKS, pretty } from '../src/lib/links.js';

describe('project links', () => {
    it('are absolute and https', () => {
        for (const [name, url] of Object.entries(LINKS)) {
            assert.ok(url.startsWith('https://'), `${name} is not https: ${url}`);
            assert.doesNotThrow(() => new URL(url), `${name} is not a url: ${url}`);
        }
    });

    it('keep the docs on the project site', () => {
        assert.ok(LINKS.docs.startsWith(LINKS.site));
    });

    it('name the author', () => {
        assert.equal(AUTHOR, 'emqnuele');
    });

    it('are shown without the scheme', () => {
        assert.equal(pretty('https://projectbea.emqnuele.dev/'), 'projectbea.emqnuele.dev');
        assert.equal(pretty(LINKS.docs), 'projectbea.emqnuele.dev/docs');
    });
});
