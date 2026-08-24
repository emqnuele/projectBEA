import React, { useCallback, useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import {
    ArrowDown, ArrowUp, Box, Eye, Hammer, Heart, MapPin, MessageSquare, Swords,
    Trash2, Utensils, X,
} from 'lucide-react';
import { cn } from '../../lib/cn';
import { Glass } from '../glass/Glass';
import { Button, IconButton } from '../ui/controls';
import { Badge } from '../ui/feedback';

const DIRECTIONS = [['north', 'N'], ['south', 'S'], ['east', 'E'], ['west', 'W']];
const EQUIP_SLOTS = [['mainhand', 'Main hand'], ['offhand', 'Off hand'], ['armor', 'Armor']];

const INITIAL_INPUTS = {
    chat: '', findBlock: '', findRadius: 50, findPillar: false, findBridge: false,
    craftItem: '', craftQty: 1, blockName: '', equipItem: '', equipDest: 'mainhand',
    attackTarget: '', discardItem: '', mineDepth: 3, bridgeCount: 5, bridgeDir: 'north',
    pillarHeight: 3, smeltInput: '', smeltFuel: '', storeName: '',
};

/**
 * Direct control of her body on the server.
 *
 * A debugging cockpit, not something the stream sees: it talks to the mod over
 * the same WebSocket she uses, so anything typed here is a command she did not
 * choose to give.
 */
export default function MinecraftConsole({ serverUrl, onClose }) {
    const [status, setStatus] = useState('connecting');
    const [data, setData] = useState({
        player: null, inventory: null, lidar: { blocks: [] }, entities: [], screenshot: null,
    });
    const [logs, setLogs] = useState([]);
    const [inputs, setInputs] = useState(INITIAL_INPUTS);
    const [moveTo, setMoveTo] = useState({ x: '', y: '', z: '' });
    const [target, setTarget] = useState({ x: '', y: '', z: '' });

    const socketRef = useRef(null);
    const retryRef = useRef(null);
    // the reconnect timer has to call the very function being defined
    const connectRef = useRef(() => { });

    const log = useCallback((source, text) => {
        setLogs((prev) => [`[${new Date().toLocaleTimeString()}] ${source}: ${text}`, ...prev].slice(0, 120));
    }, []);

    const connect = useCallback(() => {
        if (socketRef.current) return;
        setStatus('connecting');
        try {
            const socket = new WebSocket(serverUrl);
            socketRef.current = socket;

            socket.onopen = () => { setStatus('connected'); log('system', 'connected to the mod'); };
            socket.onclose = () => {
                setStatus('disconnected');
                socketRef.current = null;
                retryRef.current = setTimeout(() => connectRef.current(), 3000);
            };
            socket.onerror = () => setStatus('error');
            socket.onmessage = (event) => {
                try {
                    const message = JSON.parse(event.data);
                    if (message.player) {
                        setData((prev) => ({
                            ...prev,
                            player: message.player,
                            inventory: message.inventory ?? prev.inventory,
                            lidar: message.lidar || prev.lidar,
                            entities: message.entities || prev.entities,
                        }));
                    } else if (message.type === 'screenshot') {
                        setData((prev) => ({ ...prev, screenshot: message.data }));
                    } else if (message.status) {
                        log(message.status, [message.result, message.message].filter(Boolean).join(' — ') || 'ok');
                    }
                } catch {
                    log('error', 'the mod sent something that is not JSON');
                }
            };
        } catch {
            setStatus('error');
        }
    }, [serverUrl, log]);

    useEffect(() => { connectRef.current = connect; }, [connect]);

    useEffect(() => {
        connect();
        return () => {
            socketRef.current?.close();
            if (retryRef.current) clearTimeout(retryRef.current);
        };
    }, [connect]);

    useEffect(() => {
        const onKey = (event) => { if (event.key === 'Escape') onClose(); };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [onClose]);

    const send = (action, parameters = {}) => {
        const socket = socketRef.current;
        if (!socket || socket.readyState !== WebSocket.OPEN) {
            log('error', 'not connected — nothing was sent');
            return;
        }
        socket.send(JSON.stringify({ action, parameters }));
        log('sent', action);
    };

    const setInput = (key, value) => setInputs((prev) => ({ ...prev, [key]: value }));
    const number = (value) => (value === '' ? undefined : parseFloat(value));

    const craftable = [
        ...(data.inventory?.context?.craftable_2x2 || []),
        ...(data.inventory?.context?.craftable_3x3 || []),
    ].filter((item, index, all) => all.findIndex((other) => other.item === item.item) === index);

    return (
        <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/60 p-3 backdrop-blur-[3px]">
            <motion.div
                initial={{ opacity: 0, scale: 0.985 }}
                animate={{ opacity: 1, scale: 1 }}
                role="dialog"
                aria-modal="true"
                aria-label="Minecraft console"
                className="h-full w-full max-w-[1500px]"
            >
                <Glass className="flex h-full flex-col overflow-hidden rounded-b4">
                    <header className="flex shrink-0 items-center gap-3 border-b border-line px-4 py-3">
                        <Box size={16} style={{ color: 'var(--flux-act)' }} />
                        <h2 className="font-display text-sm font-semibold text-text">Her body</h2>
                        <Badge
                            dot
                            color={status === 'connected' ? 'var(--flux-act)' : 'var(--flux-err)'}
                        >
                            {status}
                        </Badge>
                        <span className="hidden truncate font-mono text-[10px] text-faint sm:block">{serverUrl}</span>
                        <IconButton label="Close the console" onClick={onClose} className="ml-auto">
                            <X size={16} />
                        </IconButton>
                    </header>

                    <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
                        {/* --- commands --- */}
                        <div className="w-full shrink-0 space-y-4 overflow-y-auto border-line p-3 lg:w-80 lg:border-r">
                            <Panel title="Move">
                                <div className="flex gap-1.5">
                                    <Coord value={moveTo.x} onChange={(v) => setMoveTo({ ...moveTo, x: v })} label="X" />
                                    <Coord value={moveTo.y} onChange={(v) => setMoveTo({ ...moveTo, y: v })} label="Y" />
                                    <Coord value={moveTo.z} onChange={(v) => setMoveTo({ ...moveTo, z: v })} label="Z" />
                                    <Button
                                        size="sm"
                                        variant="primary"
                                        onClick={() => send('move_to', {
                                            x: number(moveTo.x), y: number(moveTo.y), z: number(moveTo.z),
                                        })}
                                    >
                                        Go
                                    </Button>
                                </div>
                                <div className="grid grid-cols-4 gap-1.5">
                                    {DIRECTIONS.map(([value, label]) => (
                                        <Button key={value} size="sm" variant="outline" onClick={() => send('look_at', { direction: value })}>
                                            {label}
                                        </Button>
                                    ))}
                                </div>
                                <Button size="sm" variant="danger" className="w-full" onClick={() => send('stop_moving')}>
                                    Stop everything
                                </Button>
                            </Panel>

                            <Panel title="Target" hint="The block the actions below act on.">
                                <div className="flex gap-1.5">
                                    <Coord value={target.x} onChange={(v) => setTarget({ ...target, x: v })} label="X" />
                                    <Coord value={target.y} onChange={(v) => setTarget({ ...target, y: v })} label="Y" />
                                    <Coord value={target.z} onChange={(v) => setTarget({ ...target, z: v })} label="Z" />
                                </div>
                                <Text value={inputs.blockName} onChange={(v) => setInput('blockName', v)} placeholder="Block name, e.g. dirt" />
                                <div className="grid grid-cols-3 gap-1.5">
                                    <Button size="sm" variant="outline" onClick={() => send('mine_block', {
                                        x: number(target.x), y: number(target.y), z: number(target.z),
                                    })}>
                                        <Hammer size={12} /> Mine
                                    </Button>
                                    <Button size="sm" variant="outline" onClick={() => send('place_block', {
                                        x: number(target.x), y: number(target.y), z: number(target.z), block: inputs.blockName,
                                    })}>
                                        <Box size={12} /> Place
                                    </Button>
                                    <Button size="sm" variant="outline" onClick={() => send('use_block', {
                                        x: number(target.x), y: number(target.y), z: number(target.z),
                                    })}>
                                        Use
                                    </Button>
                                </div>
                            </Panel>

                            <Panel title="Find">
                                <div className="flex gap-1.5">
                                    <Text value={inputs.findBlock} onChange={(v) => setInput('findBlock', v)} placeholder="wood" />
                                    <Coord value={inputs.findRadius} onChange={(v) => setInput('findRadius', v)} label="R" />
                                    <Button size="sm" variant="primary" onClick={() => send('find_block', {
                                        block: inputs.findBlock,
                                        radius: parseInt(inputs.findRadius, 10) || 50,
                                        allowPillaring: inputs.findPillar,
                                        allowBridging: inputs.findBridge,
                                    })}>
                                        Find
                                    </Button>
                                </div>
                                <div className="flex gap-4">
                                    <Check checked={inputs.findPillar} onChange={(v) => setInput('findPillar', v)} label="May pillar" />
                                    <Check checked={inputs.findBridge} onChange={(v) => setInput('findBridge', v)} label="May bridge" />
                                </div>
                            </Panel>

                            <Panel title="Terrain">
                                <div className="flex gap-1.5">
                                    <Coord value={inputs.pillarHeight} onChange={(v) => setInput('pillarHeight', v)} label="H" />
                                    <Button size="sm" variant="outline" className="flex-1" onClick={() => send('pillar_up', {
                                        height: parseInt(inputs.pillarHeight, 10) || 1, block: inputs.blockName,
                                    })}>
                                        <ArrowUp size={12} /> Pillar up
                                    </Button>
                                </div>
                                <div className="flex gap-1.5">
                                    <Coord value={inputs.mineDepth} onChange={(v) => setInput('mineDepth', v)} label="D" />
                                    <Button size="sm" variant="outline" className="flex-1" onClick={() => send('mine_down', {
                                        depth: parseInt(inputs.mineDepth, 10) || 1,
                                    })}>
                                        <ArrowDown size={12} /> Mine down
                                    </Button>
                                </div>
                                <div className="flex gap-1.5">
                                    <Coord value={inputs.bridgeCount} onChange={(v) => setInput('bridgeCount', v)} label="#" />
                                    <select
                                        value={inputs.bridgeDir}
                                        onChange={(e) => setInput('bridgeDir', e.target.value)}
                                        aria-label="Bridge direction"
                                        className="rounded-b1 border border-line bg-fill px-1.5 text-[11px] text-text outline-none"
                                    >
                                        {DIRECTIONS.map(([value, label]) => (
                                            <option key={value} value={value}>{label}</option>
                                        ))}
                                    </select>
                                    <Button size="sm" variant="outline" className="flex-1" onClick={() => send('bridge', {
                                        count: parseInt(inputs.bridgeCount, 10) || 1, direction: inputs.bridgeDir,
                                    })}>
                                        Bridge
                                    </Button>
                                </div>
                                <Button size="sm" variant="outline" className="w-full" onClick={() => send('bridge', {
                                    x: number(target.x), z: number(target.z),
                                })}>
                                    Bridge to the target
                                </Button>
                            </Panel>

                            <Panel title="Craft" hint={`${craftable.length} recipes she can make right now`}>
                                <div className="flex gap-1.5">
                                    <Text value={inputs.craftItem} onChange={(v) => setInput('craftItem', v)} placeholder="stick" />
                                    <Coord value={inputs.craftQty} onChange={(v) => setInput('craftQty', v)} label="Qty" />
                                    <Button size="sm" variant="primary" onClick={() => send('craft_item', {
                                        item: inputs.craftItem, quantity: parseInt(inputs.craftQty, 10) || 1,
                                    })}>
                                        Craft
                                    </Button>
                                </div>
                                {craftable.length > 0 && (
                                    <div className="flex max-h-24 flex-wrap gap-1 overflow-y-auto">
                                        {craftable.slice(0, 18).map((recipe) => (
                                            <button
                                                key={recipe.item}
                                                onClick={() => { setInput('craftItem', recipe.item.replace('minecraft:', '')); setInput('craftQty', 1); }}
                                                title={`up to ${recipe.max_craftable}`}
                                                className="max-w-[8rem] truncate rounded border border-line px-1.5 py-0.5 font-mono text-[9px] text-dim transition-colors hover:border-line-strong hover:text-text"
                                            >
                                                {recipe.item.replace('minecraft:', '')}
                                            </button>
                                        ))}
                                    </div>
                                )}
                            </Panel>

                            <Panel title="Containers">
                                <div className="flex gap-1.5">
                                    <Text value={inputs.smeltInput} onChange={(v) => setInput('smeltInput', v)} placeholder="Input" />
                                    <Text value={inputs.smeltFuel} onChange={(v) => setInput('smeltFuel', v)} placeholder="Fuel" />
                                    <Button size="sm" variant="outline" onClick={() => send('smelt_item', {
                                        input_item: inputs.smeltInput, fuel_item: inputs.smeltFuel,
                                    })}>
                                        Smelt
                                    </Button>
                                </div>
                                <div className="flex gap-1.5">
                                    <Text value={inputs.storeName} onChange={(v) => setInput('storeName', v)} placeholder="Item" />
                                    <Button size="sm" variant="outline" onClick={() => send('store_item', { item: inputs.storeName })}>Store</Button>
                                    <Button size="sm" variant="outline" onClick={() => send('retrieve_item', { item: inputs.storeName })}>Take</Button>
                                </div>
                            </Panel>

                            <Panel title="Inventory">
                                <div className="flex gap-1.5">
                                    <Text value={inputs.equipItem} onChange={(v) => setInput('equipItem', v)} placeholder="Item to equip" />
                                    <select
                                        value={inputs.equipDest}
                                        onChange={(e) => setInput('equipDest', e.target.value)}
                                        aria-label="Where to equip it"
                                        className="rounded-b1 border border-line bg-fill px-1.5 text-[11px] text-text outline-none"
                                    >
                                        {EQUIP_SLOTS.map(([value, label]) => (
                                            <option key={value} value={value}>{label}</option>
                                        ))}
                                    </select>
                                    <Button size="sm" variant="outline" onClick={() => send('equip_item', {
                                        item: inputs.equipItem, destination: inputs.equipDest,
                                    })}>
                                        Equip
                                    </Button>
                                </div>
                                <div className="flex gap-1.5">
                                    <Text value={inputs.discardItem} onChange={(v) => setInput('discardItem', v)} placeholder="Item to throw away" />
                                    <IconButton label="Throw it away" size="sm" variant="danger" onClick={() => send('discard_item', { item: inputs.discardItem })}>
                                        <Trash2 size={12} />
                                    </IconButton>
                                    <IconButton label="Eat something" size="sm" variant="outline" onClick={() => send('eat_food', {})}>
                                        <Utensils size={12} />
                                    </IconButton>
                                </div>
                            </Panel>

                            <Panel title="Fight">
                                <div className="flex gap-1.5">
                                    <Text value={inputs.attackTarget} onChange={(v) => setInput('attackTarget', v)} placeholder="Entity id or name" />
                                    <Button size="sm" variant="danger" onClick={() => {
                                        const raw = inputs.attackTarget;
                                        const parsed = Number.parseInt(raw, 10);
                                        send('attack_entity', { target: Number.isNaN(parsed) ? raw : parsed });
                                    }}>
                                        <Swords size={12} /> Attack
                                    </Button>
                                </div>
                            </Panel>

                            <Panel title="Say something">
                                <div className="flex gap-1.5">
                                    <Text
                                        value={inputs.chat}
                                        onChange={(v) => setInput('chat', v)}
                                        placeholder="Into the game chat"
                                        onEnter={() => { send('chat', { message: inputs.chat }); setInput('chat', ''); }}
                                    />
                                    <IconButton label="Send to game chat" size="sm" variant="primary" onClick={() => {
                                        send('chat', { message: inputs.chat });
                                        setInput('chat', '');
                                    }}>
                                        <MessageSquare size={13} />
                                    </IconButton>
                                </div>
                            </Panel>
                        </div>

                        {/* --- what she can see --- */}
                        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
                            <div className="flex min-h-0 flex-1 flex-col border-b border-line lg:flex-row">
                                <div className="flex min-h-0 flex-1 flex-col p-3">
                                    <div className="mb-2 flex items-center justify-between">
                                        <h3 className="font-display text-[12px] font-semibold text-text">What she sees</h3>
                                        <Button size="sm" variant="outline" onClick={() => send('request_screenshot')}>
                                            <Eye size={12} /> Refresh
                                        </Button>
                                    </div>
                                    <div className="grid min-h-0 flex-1 place-items-center overflow-hidden rounded-b2 border border-line bg-sunk">
                                        {data.screenshot ? (
                                            <img
                                                alt="Her current view of the world"
                                                src={`data:image/png;base64,${data.screenshot}`}
                                                className="h-full w-full object-contain"
                                            />
                                        ) : (
                                            <span className="font-mono text-[11px] text-faint">no image yet</span>
                                        )}
                                    </div>
                                </div>

                                <div className="flex min-h-0 flex-col p-3 lg:w-[22rem]">
                                    <h3 className="mb-2 font-display text-[12px] font-semibold text-text">Log</h3>
                                    <div className="min-h-0 flex-1 overflow-y-auto rounded-b2 border border-line bg-sunk p-2">
                                        {logs.length === 0 ? (
                                            <p className="py-4 text-center font-mono text-[11px] text-faint">nothing yet</p>
                                        ) : logs.map((line, index) => (
                                            <p key={index} className="break-words border-b border-line py-0.5 font-mono text-[10.5px] text-dim last:border-0">
                                                {line}
                                            </p>
                                        ))}
                                    </div>
                                </div>
                            </div>

                            <div className="flex min-h-0 flex-1 flex-col gap-3 p-3 lg:flex-row">
                                <div className="flex min-h-0 flex-col gap-3 lg:w-60">
                                    <div className="space-y-2 rounded-b2 border border-line bg-fill p-3">
                                        <Stat
                                            icon={MapPin}
                                            label="Position"
                                            value={data.player
                                                ? `${data.player.position.x.toFixed(1)}, ${data.player.position.y.toFixed(1)}, ${data.player.position.z.toFixed(1)}`
                                                : 'unknown'}
                                        />
                                        <Stat
                                            icon={Heart}
                                            label="Health"
                                            value={`${data.player?.health?.toFixed(0) ?? 0} / 20`}
                                            color="var(--flux-err)"
                                        />
                                        <Stat
                                            icon={Utensils}
                                            label="Food"
                                            value={`${data.player?.food ?? 0} / 20`}
                                            color="var(--vital)"
                                        />
                                    </div>

                                    <div className="min-h-0 flex-1 overflow-y-auto rounded-b2 border border-line bg-fill p-2">
                                        <p className="sticky top-0 bg-transparent pb-1 font-mono text-[9px] uppercase tracking-wider text-faint">
                                            Around her — click to target
                                        </p>
                                        {data.lidar.blocks.slice(0, 60).map((block, index) => (
                                            <button
                                                key={`${block.x}-${block.y}-${block.z}-${index}`}
                                                onClick={() => {
                                                    setMoveTo({ x: block.x, y: block.y + 1, z: block.z });
                                                    setTarget({ x: block.x, y: block.y, z: block.z });
                                                }}
                                                className="block w-full truncate rounded px-1 text-left font-mono text-[10px] text-faint transition-colors hover:bg-fill-2 hover:text-text"
                                            >
                                                [{block.x},{block.y},{block.z}] {block.name.replace('minecraft:', '')}
                                            </button>
                                        ))}
                                    </div>
                                </div>

                                <div className="flex min-h-0 flex-1 flex-col gap-3">
                                    <div className="rounded-b2 border border-line bg-fill p-3">
                                        <p className="mb-2 font-mono text-[9px] uppercase tracking-wider text-faint">Hotbar</p>
                                        <div className="flex flex-wrap justify-center gap-1">
                                            {data.inventory?.hotbar?.map((slot, index) => (
                                                <Slot
                                                    key={slot?.slot ?? `hotbar-${index}`}
                                                    slot={slot}
                                                    selected={slot && slot.slot === data.inventory.selected_slot}
                                                    onClick={() => slot && send('select_slot', { slot: slot.slot })}
                                                />
                                            ))}
                                        </div>
                                    </div>
                                    <div className="min-h-0 flex-1 overflow-y-auto rounded-b2 border border-line bg-fill p-3">
                                        <p className="mb-2 font-mono text-[9px] uppercase tracking-wider text-faint">Inventory</p>
                                        <div className="mx-auto grid w-fit grid-cols-9 gap-1">
                                            {data.inventory?.main?.map((slot, index) => (
                                                <Slot key={slot?.slot ?? `main-${index}`} slot={slot} />
                                            ))}
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </Glass>
            </motion.div>
        </div>
    );
}

function Panel({ title, hint, children }) {
    return (
        <section className="space-y-2">
            <div className="flex items-baseline gap-2">
                <h3 className="font-mono text-[9px] font-bold uppercase tracking-wider text-faint">{title}</h3>
                {hint && <span className="truncate text-[10px] text-faint">{hint}</span>}
            </div>
            {children}
        </section>
    );
}

const FIELD =
    'min-w-0 rounded-b1 border border-line bg-fill px-2 py-1 text-[11px] text-text ' +
    'outline-none transition-colors placeholder:text-faint focus:border-line-strong';

function Coord({ value, onChange, label }) {
    return (
        <input
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder={label}
            aria-label={label}
            className={cn(FIELD, 'w-12 text-center font-mono')}
        />
    );
}

function Text({ value, onChange, placeholder, onEnter }) {
    return (
        <input
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && onEnter) onEnter(); }}
            placeholder={placeholder}
            aria-label={placeholder}
            className={cn(FIELD, 'flex-1')}
        />
    );
}

function Check({ checked, onChange, label }) {
    return (
        <label className="flex cursor-pointer items-center gap-1.5 text-[10px] text-dim">
            <input
                type="checkbox"
                checked={checked}
                onChange={(e) => onChange(e.target.checked)}
                className="h-3 w-3 accent-[color:var(--vital)]"
            />
            {label}
        </label>
    );
}

function Stat({ icon: Icon, label, value, color }) {
    return (
        <div className="flex items-center gap-2">
            <Icon size={12} className="shrink-0 text-faint" />
            <span className="text-[11px] text-faint">{label}</span>
            <span className="ml-auto truncate font-mono text-[11px]" style={{ color: color || 'var(--text)' }}>
                {value}
            </span>
        </div>
    );
}

function Slot({ slot, selected, onClick }) {
    if (!slot) {
        return <span className="h-9 w-9 rounded-b1 border border-line bg-sunk" />;
    }
    return (
        <button
            onClick={onClick}
            title={slot.item}
            className={cn(
                'relative grid h-9 w-9 place-items-center rounded-b1 border transition-colors',
                selected ? 'border-transparent' : 'border-line bg-sunk hover:border-line-strong',
            )}
            style={selected ? {
                background: 'var(--vital-soft)',
                boxShadow: 'inset 0 0 0 1px color-mix(in srgb, var(--vital) 55%, transparent)',
            } : undefined}
        >
            {slot.count > 0 && (
                <>
                    <span className="px-0.5 text-center font-mono text-[8px] leading-tight text-dim">
                        {slot.item?.replace('minecraft:', '').slice(0, 4)}
                    </span>
                    <span className="absolute -bottom-1 -right-1 rounded-full border border-line bg-bg px-1 font-mono text-[8px] text-text">
                        {slot.count}
                    </span>
                </>
            )}
        </button>
    );
}
