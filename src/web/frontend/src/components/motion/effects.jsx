import React, { useEffect, useRef, useState } from 'react';
import { animate, motion, useMotionValue, useSpring, useTransform } from 'framer-motion';
import { cn } from '../../lib/cn';

const reduced = () =>
    typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/** A number that travels to its new value instead of jumping. */
export function CountUp({ value = 0, format = (n) => Math.round(n), duration = 0.7, className }) {
    const motionValue = useMotionValue(value);
    const [display, setDisplay] = useState(() => format(value));

    useEffect(() => {
        if (reduced()) {
            setDisplay(format(value));
            return undefined;
        }
        const controls = animate(motionValue, value, {
            duration,
            ease: [0.16, 1, 0.3, 1],
            onUpdate: (latest) => setDisplay(format(latest)),
        });
        return () => controls.stop();
    }, [value, duration, format, motionValue]);

    return <span className={cn('tnum', className)}>{display}</span>;
}

/** Characters arriving one after another. Used once, on the way in. */
export function SplitText({ text, className, delay = 0, stagger = 0.028 }) {
    const characters = String(text).split('');
    return (
        <span className={className} aria-label={text}>
            {characters.map((character, index) => (
                <motion.span
                    key={`${character}-${index}`}
                    aria-hidden="true"
                    className="inline-block whitespace-pre"
                    initial={{ opacity: 0, y: '0.35em', filter: 'blur(6px)' }}
                    animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
                    transition={{ delay: delay + index * stagger, duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
                >
                    {character}
                </motion.span>
            ))}
        </span>
    );
}

/** The control leans toward the cursor before you reach it. */
export function Magnetic({ children, strength = 0.28, className }) {
    const ref = useRef(null);
    const x = useSpring(useMotionValue(0), { stiffness: 320, damping: 22 });
    const y = useSpring(useMotionValue(0), { stiffness: 320, damping: 22 });

    const onMove = (event) => {
        if (reduced()) return;
        const box = ref.current?.getBoundingClientRect();
        if (!box) return;
        x.set((event.clientX - (box.left + box.width / 2)) * strength);
        y.set((event.clientY - (box.top + box.height / 2)) * strength);
    };

    return (
        <motion.div
            ref={ref}
            style={{ x, y }}
            onMouseMove={onMove}
            onMouseLeave={() => { x.set(0); y.set(0); }}
            className={cn('inline-flex', className)}
        >
            {children}
        </motion.div>
    );
}

/** A tile that catches the light where the cursor is. */
export function Spotlight({ children, className, color = 'rgb(255 255 255 / 7%)', ...props }) {
    const ref = useRef(null);
    const [position, setPosition] = useState(null);

    const onMove = (event) => {
        const box = ref.current?.getBoundingClientRect();
        if (!box) return;
        setPosition({ x: event.clientX - box.left, y: event.clientY - box.top });
    };

    return (
        <div
            ref={ref}
            onMouseMove={onMove}
            onMouseLeave={() => setPosition(null)}
            className={cn('relative', className)}
            {...props}
        >
            <span
                aria-hidden="true"
                className="pointer-events-none absolute inset-0 rounded-[inherit] opacity-0 transition-opacity duration-300"
                style={position ? {
                    opacity: 1,
                    background: `radial-gradient(340px circle at ${position.x}px ${position.y}px, ${color}, transparent 70%)`,
                } : undefined}
            />
            {children}
        </div>
    );
}

/**
 * A lucide icon that reacts instead of sitting still: `spin` while something is
 * running, `pulse` while she is live, `bounce` on the way in.
 */
export function AnimatedIcon({ icon: Icon, state = 'idle', size = 16, className, strokeWidth = 2 }) {
    const animations = {
        idle: {},
        spin: { rotate: 360, transition: { duration: 1.1, repeat: Infinity, ease: 'linear' } },
        pulse: { scale: [1, 1.16, 1], opacity: [0.75, 1, 0.75], transition: { duration: 1.6, repeat: Infinity, ease: 'easeInOut' } },
        bounce: { y: [0, -2, 0], transition: { duration: 1.4, repeat: Infinity, ease: 'easeInOut' } },
        breathe: { opacity: [0.5, 1, 0.5], transition: { duration: 2.6, repeat: Infinity, ease: 'easeInOut' } },
    };

    return (
        <motion.span
            className={cn('inline-grid place-items-center', className)}
            animate={animations[state] || animations.idle}
        >
            <Icon size={size} strokeWidth={strokeWidth} />
        </motion.span>
    );
}

/** A ring that fills. Used for plan progress, where a bar would be one more bar. */
export function ProgressRing({ value = 0, size = 44, thickness = 3, color = 'var(--vital)', children }) {
    const radius = (size - thickness) / 2;
    const circumference = 2 * Math.PI * radius;
    const progress = useSpring(0, { stiffness: 120, damping: 24 });
    const offset = useTransform(progress, (v) => circumference * (1 - v));

    useEffect(() => { progress.set(Math.max(0, Math.min(1, value))); }, [value, progress]);

    return (
        <div className="relative grid place-items-center" style={{ width: size, height: size }}>
            <svg width={size} height={size} className="-rotate-90">
                <circle
                    cx={size / 2} cy={size / 2} r={radius}
                    fill="none" stroke="var(--line)" strokeWidth={thickness}
                />
                <motion.circle
                    cx={size / 2} cy={size / 2} r={radius}
                    fill="none" stroke={color} strokeWidth={thickness} strokeLinecap="round"
                    strokeDasharray={circumference}
                    style={{ strokeDashoffset: offset }}
                />
            </svg>
            {children && <span className="absolute inset-0 grid place-items-center">{children}</span>}
        </div>
    );
}
