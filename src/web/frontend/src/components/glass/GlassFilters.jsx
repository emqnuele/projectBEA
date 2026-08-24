import React from 'react';
import { useAppearance } from '../../state/AppearanceProvider';

/**
 * The refraction behind every glass surface.
 *
 * Blur alone reads as frosted plastic. What makes it glass is that the backdrop
 * *bends*: feTurbulence generates the irregularity of a liquid surface and
 * feDisplacementMap pushes the pixels of the backdrop along it. The CSS mask on
 * `.glass::after` keeps that bend at the rim, where a real lens is thickest.
 *
 * Dispersion is the same displacement run three times at slightly different
 * strengths, one per channel, recombined — which is exactly why the edge of a
 * real lens fringes into colour.
 *
 * Mounted once, at the root: filters are referenced by id from CSS.
 */
export function GlassFilters() {
    const { settings } = useAppearance();
    const refraction = settings.refraction;
    const dispersion = settings.dispersion;

    return (
        <svg
            aria-hidden="true"
            focusable="false"
            width="0"
            height="0"
            style={{ position: 'absolute', width: 0, height: 0, overflow: 'hidden' }}
        >
            <defs>
                <filter
                    id="lg-refract"
                    x="-25%" y="-25%" width="150%" height="150%"
                    colorInterpolationFilters="sRGB"
                >
                    <feTurbulence
                        type="fractalNoise"
                        baseFrequency="0.0055 0.009"
                        numOctaves="2"
                        seed="17"
                        result="noise"
                    />
                    <feGaussianBlur in="noise" stdDeviation="1.4" result="softNoise" />
                    <feDisplacementMap
                        in="SourceGraphic"
                        in2="softNoise"
                        scale={refraction}
                        xChannelSelector="R"
                        yChannelSelector="G"
                    />
                </filter>

                <filter
                    id="lg-disperse"
                    x="-25%" y="-25%" width="150%" height="150%"
                    colorInterpolationFilters="sRGB"
                >
                    <feTurbulence
                        type="fractalNoise"
                        baseFrequency="0.0055 0.009"
                        numOctaves="2"
                        seed="17"
                        result="noise"
                    />
                    <feGaussianBlur in="noise" stdDeviation="1.4" result="softNoise" />

                    {/* red bends most, blue least — the order a prism puts them in */}
                    <feDisplacementMap
                        in="SourceGraphic" in2="softNoise" scale={dispersion * 1.5}
                        xChannelSelector="R" yChannelSelector="G" result="shiftR"
                    />
                    <feColorMatrix
                        in="shiftR" type="matrix" result="onlyR"
                        values="1 0 0 0 0
                                0 0 0 0 0
                                0 0 0 0 0
                                0 0 0 1 0"
                    />
                    <feDisplacementMap
                        in="SourceGraphic" in2="softNoise" scale={dispersion}
                        xChannelSelector="R" yChannelSelector="G" result="shiftG"
                    />
                    <feColorMatrix
                        in="shiftG" type="matrix" result="onlyG"
                        values="0 0 0 0 0
                                0 1 0 0 0
                                0 0 0 0 0
                                0 0 0 1 0"
                    />
                    <feDisplacementMap
                        in="SourceGraphic" in2="softNoise" scale={dispersion * 0.5}
                        xChannelSelector="R" yChannelSelector="G" result="shiftB"
                    />
                    <feColorMatrix
                        in="shiftB" type="matrix" result="onlyB"
                        values="0 0 0 0 0
                                0 0 0 0 0
                                0 0 1 0 0
                                0 0 0 1 0"
                    />

                    <feBlend in="onlyR" in2="onlyG" mode="screen" result="rg" />
                    <feBlend in="rg" in2="onlyB" mode="screen" />
                </filter>
            </defs>
        </svg>
    );
}
