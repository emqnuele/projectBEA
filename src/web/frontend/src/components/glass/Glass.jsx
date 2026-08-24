import React, { forwardRef } from 'react';
import { motion } from 'framer-motion';
import { cn } from '../../lib/cn';
import { useAppearance } from '../../state/AppearanceProvider';

/**
 * A liquid glass surface.
 *
 * `quiet` drops the SVG refraction for the many small tiles that would otherwise
 * each cost a filtered backdrop — the rim light and the frost are kept, so they
 * still belong to the same material.
 */
export const Glass = forwardRef(function Glass(
    { as: Tag = 'div', quiet = false, sheen = true, className, children, style, ...props },
    ref,
) {
    const { settings } = useAppearance();
    const refracting = settings.glass && !quiet;

    return (
        <Tag
            ref={ref}
            className={cn(refracting ? 'glass' : 'glass-quiet', className)}
            style={style}
            {...props}
        >
            {refracting && settings.dispersion > 0 && <span className="glass-dispersion" aria-hidden="true" />}
            {sheen && <span className="glass-sheen" aria-hidden="true" />}
            {children}
        </Tag>
    );
});

export const MotionGlass = motion.create(Glass);
