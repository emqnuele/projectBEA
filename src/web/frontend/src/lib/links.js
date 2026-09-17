/**
 * Where the project lives, in one place.
 *
 * Three of these were already spelled out in a component each, which is how a
 * moved docs site becomes four dead links instead of one.
 */

export const AUTHOR = 'emqnuele';

export const LINKS = {
    site: 'https://projectbea.emqnuele.dev',
    docs: 'https://projectbea.emqnuele.dev/docs',
    repo: 'https://github.com/emqnuele/projectBEA',
    author: 'https://emanuelefaraci.com',
};

/** What to show for a link: the host and path, without the scheme. */
export function pretty(url) {
    return url.replace(/^https?:\/\//, '').replace(/\/$/, '');
}
