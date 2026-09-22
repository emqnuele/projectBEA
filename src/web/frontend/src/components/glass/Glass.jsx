import React, { forwardRef } from 'react';
import { cn } from '../../lib/cn';

/**
 * A liquid glass surface.
 * `quiet` drops the SVG refraction for small tiles.
 */
export const Glass = forwardRef(function Glass(
    { as: Tag = 'div', quiet = false, sheen = true, className, children, style, ...props },
    ref,
) {
    return (
        <Tag
            ref={ref}
            className={cn(quiet ? 'glass-quiet' : 'glass', className)}
            style={style}
            {...props}
        >
            {sheen && !quiet && <span className="glass-sheen" aria-hidden="true" />}
            {children}
        </Tag>
    );
});
