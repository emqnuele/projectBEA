import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '../ui/card';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Badge } from '../ui/badge';
import { ScrollArea } from '../ui/scroll-area';
import { Separator } from '../ui/separator';
import { X, Send, Eye, Crosshair, Hammer, Shield, Box, ArrowUp, ArrowDown, ArrowLeft, ArrowRight, Activity, Map, MessageSquare, Utensils, Trash2, ArrowBigUp } from 'lucide-react';
import { Switch } from '../ui/switch';

export default function MinecraftConsole({ serverUrl, onClose }) {
    const [status, setStatus] = useState('disconnected'); // disconnected, connected, error
    const [data, setData] = useState({
        player: null,
        inventory: null,
        lidar: { blocks: [] },
        entities: [],
        gui_state: null,
        screenshot: null
    });
    const [logs, setLogs] = useState([]);
    const wsRef = useRef(null);
    const reconnectTimeoutRef = useRef(null);

    // --- connection logic ---
    const connect = useCallback(() => {
        if (wsRef.current) return;

        setStatus('connecting');
        console.log(`[MC-Console] Connecting to ${serverUrl}...`);

        try {
            const ws = new WebSocket(serverUrl);
            wsRef.current = ws;

            ws.onopen = () => {
                console.log("[MC-Console] Connected!");
                setStatus('connected');
                addLog("System", "Connected to Minecraft Mod.");
            };

            ws.onmessage = (event) => {
                try {
                    const msg = JSON.parse(event.data);
                    handleMessage(msg);
                } catch (e) {
                    console.error("JSON Error", e);
                }
            };

            ws.onclose = () => {
                console.log("[MC-Console] Disconnected.");
                setStatus('disconnected');
                wsRef.current = null;
                reconnectTimeoutRef.current = setTimeout(connect, 3000);
            };

            ws.onerror = (err) => {
                console.error("[MC-Console] Error", err);
                setStatus('error');
            };
        } catch (e) {
            console.error("Connection failed", e);
            setStatus('error');
        }

    }, [serverUrl]);

    useEffect(() => {
        connect();
        return () => {
            if (wsRef.current) wsRef.current.close();
            if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
        };
    }, [connect]);


    const handleMessage = (msg) => {
        if (msg.player) {
            setData(prev => ({
                ...prev,
                player: msg.player,
                inventory: msg.inventory,
                lidar: msg.lidar || prev.lidar,
                entities: msg.entities || prev.entities,
                gui_state: msg.gui_state || prev.gui_state
            }));
        } else if (msg.status) {
            const text = `${msg.status} ${msg.result ? ': ' + msg.result : ''} ${msg.message ? '(' + msg.message + ')' : ''}`;
            addLog("Event", text);
        } else if (msg.type === "screenshot") {
            setData(prev => ({ ...prev, screenshot: msg.data }));
        }
    };

    const addLog = (source, text) => {
        setLogs(prev => [`[${new Date().toLocaleTimeString()}] [${source}] ${text}`, ...prev].slice(0, 100));
    };


    // --- command sending ---
    const send = (action, params = {}) => {
        if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
            addLog("Error", "Not connected.");
            return;
        }
        const cmd = { action, parameters: params };
        wsRef.current.send(JSON.stringify(cmd));
        addLog("Sent", `${action}`);
    };

    // --- input states ---
    const [moveCoords, setMoveCoords] = useState({ x: '', y: '', z: '' });
    const [actCoords, setActCoords] = useState({ x: '', y: '', z: '' });
    const [inputs, setInputs] = useState({
        chat: '',
        findBlock: '', findRadius: 50, findPillar: false, findBridge: false,
        craftItem: '', craftQty: 1,
        blockName: '',
        equipItem: '', equipDest: 'mainhand',
        attackTarget: '',
        discardItem: '',
        mineDepth: 3, bridgeCount: 5, bridgeDir: 'north', pillarHeight: 3,
        smeltInput: '', smeltFuel: '',
        storeName: ''
    });

    const updateInput = (k, v) => setInputs(prev => ({ ...prev, [k]: v }));

    // --- helper functions ---
    const renderSlot = (slot, isHotbar = false, selectedSlot = -1) => {
        const sizeClass = "w-11 h-11"; // Larger slots

        // empty slot
        if (!slot) return <div className={`${sizeClass} bg-gray-300/20 border-2 border-gray-300 rounded-md shadow-inner`}></div>;

        const isSelected = isHotbar && slot.slot === selectedSlot;

        return (
            <div
                key={slot.slot}
                className={`${sizeClass} relative flex items-center justify-center border-2 rounded-md cursor-pointer transition-all duration-100
                ${isSelected
                        ? 'border-blue-500 bg-blue-50 shadow-[0_0_10px_rgba(59,130,246,0.2)] scale-105 z-10'
                        : 'border-gray-400 bg-white hover:border-gray-500 hover:bg-gray-50 shadow-sm'}`}
                title={slot.item}
                onClick={() => isHotbar && send("select_slot", { slot: slot.slot })}
            >
                {slot.count > 0 && (
                    <>
                        {/* item icon / text placeholder */}
                        <span className="text-[10px] leading-tight text-center break-all px-0.5 text-gray-700 font-bold tracking-tight">
                            {slot.item?.replace("minecraft:", "").slice(0, 4)}
                        </span>

                        {/* count badge */}
                        <div className="absolute -bottom-1 -right-1 bg-gray-800 text-white text-[9px] font-bold px-1 rounded-full border border-gray-600 min-w-[16px] text-center shadow-md">
                            {slot.count}
                        </div>
                    </>
                )}
            </div>
        );
    };

    const bridgeOptions = [
        { value: 'north', label: 'N' }, { value: 'south', label: 'S' },
        { value: 'east', label: 'E' }, { value: 'west', label: 'W' }
    ];

    const equipOptions = [
        { value: 'mainhand', label: 'Main' }, { value: 'offhand', label: 'Off' }, { value: 'armor', label: 'Armor' } // armor logic handled by backend? usually head/chest/etc. stick to simple for now.
    ];

    if (!data) return null;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
            {/* light theme container */}
            <div className="bg-white w-full max-w-7xl h-[90vh] rounded-xl shadow-2xl overflow-hidden border border-gray-200 flex flex-col text-gray-900">
                {/* header */}
                <div className="h-14 border-b border-gray-200 flex items-center justify-between px-6 bg-gray-50">
                    <div className="flex items-center gap-4">
                        <h2 className="text-lg font-bold text-gray-800 flex items-center gap-2">
                            <Activity className="w-5 h-5 text-blue-600" />
                            Minecraft Console
                        </h2>
                        <Badge variant="outline" className={`${status === 'connected' ? 'bg-green-100 text-green-700 border-green-200' : 'bg-red-100 text-red-700 border-red-200'}`}>
                            {status.toUpperCase()}
                        </Badge>
                        <span className="text-xs text-gray-400 font-mono">{serverUrl}</span>
                    </div>
                    <Button variant="ghost" size="icon" onClick={onClose} className="hover:bg-red-50 hover:text-red-600">
                        <X className="w-5 h-5" />
                    </Button>
                </div>

                {/* BODY */}
                <div className="flex-1 flex overflow-hidden">

                    {/* SIDEBAR: CONTROLS */}
                    <div className="w-80 bg-gray-50 border-r border-gray-200 flex flex-col overflow-y-auto p-4 gap-6">

                        {/* Move To */}
                        <div className="space-y-2">
                            <Label className="text-xs text-gray-500 uppercase tracking-wider font-bold">Movement</Label>
                            <div className="flex gap-1">
                                <Input placeholder="X" className="h-8 bg-white text-xs" value={moveCoords.x} onChange={e => setMoveCoords({ ...moveCoords, x: e.target.value })} />
                                <Input placeholder="Y" className="h-8 bg-white text-xs" value={moveCoords.y} onChange={e => setMoveCoords({ ...moveCoords, y: e.target.value })} />
                                <Input placeholder="Z" className="h-8 bg-white text-xs" value={moveCoords.z} onChange={e => setMoveCoords({ ...moveCoords, z: e.target.value })} />
                                <Button size="sm" className="h-8 bg-blue-600 hover:bg-blue-700 text-white" onClick={() => send("move_to", { x: parseFloat(moveCoords.x), y: parseFloat(moveCoords.y), z: parseFloat(moveCoords.z) })}>Go</Button>
                            </div>
                            <div className="grid grid-cols-4 gap-1">
                                <Button variant="outline" size="sm" className="h-7 text-[10px]" onClick={() => send("look_at", { direction: "north" })}>N</Button>
                                <Button variant="outline" size="sm" className="h-7 text-[10px]" onClick={() => send("look_at", { direction: "south" })}>S</Button>
                                <Button variant="outline" size="sm" className="h-7 text-[10px]" onClick={() => send("look_at", { direction: "east" })}>E</Button>
                                <Button variant="outline" size="sm" className="h-7 text-[10px]" onClick={() => send("look_at", { direction: "west" })}>W</Button>
                            </div>
                            <Button variant="destructive" size="sm" className="w-full h-7 text-xs bg-red-600 hover:bg-red-700 text-white" onClick={() => send("stop_moving")}>STOP ALL MOVEMENT</Button>
                        </div>

                        <Separator />

                        {/* actions target */}
                        <div className="space-y-3">
                            <Label className="text-xs text-gray-500 uppercase tracking-wider font-bold">Action Target</Label>
                            <div className="flex gap-1 items-center">
                                <span className="text-[10px] text-gray-400 w-6">TGT</span>
                                <Input placeholder="X" className="h-7 bg-white text-[10px]" value={actCoords.x} onChange={e => setActCoords({ ...actCoords, x: e.target.value })} />
                                <Input placeholder="Y" className="h-7 bg-white text-[10px]" value={actCoords.y} onChange={e => setActCoords({ ...actCoords, y: e.target.value })} />
                                <Input placeholder="Z" className="h-7 bg-white text-[10px]" value={actCoords.z} onChange={e => setActCoords({ ...actCoords, z: e.target.value })} />
                            </div>
                        </div>

                        {/* find */}
                        <div className="space-y-2">
                            <div className="flex gap-1">
                                <Input placeholder="Find (e.g. wood)" className="h-7 bg-white text-[10px]" value={inputs.findBlock} onChange={e => updateInput('findBlock', e.target.value)} />
                                <Input placeholder="R" className="h-7 w-12 bg-white text-[10px]" value={inputs.findRadius} onChange={e => updateInput('findRadius', e.target.value)} />
                                <Button size="sm" className="h-7 text-[10px]" onClick={() => send("find_block", { block: inputs.findBlock, radius: parseInt(inputs.findRadius), allowPillaring: inputs.findPillar, allowBridging: inputs.findBridge })}>Find</Button>
                            </div>
                            <div className="flex gap-4 text-[10px]">
                                <label className="flex items-center gap-1"><input type="checkbox" checked={inputs.findPillar} onChange={e => updateInput('findPillar', e.target.checked)} /> Pillar</label>
                                <label className="flex items-center gap-1"><input type="checkbox" checked={inputs.findBridge} onChange={e => updateInput('findBridge', e.target.checked)} /> Bridge</label>
                            </div>
                        </div>

                        <Separator />

                        {/* vertical & bridge */}
                        <div className="space-y-2">
                            {/* pillar up */}
                            <div className="flex gap-1">
                                <Input placeholder="H" className="h-7 w-12 bg-white text-[10px]" value={inputs.pillarHeight} onChange={e => updateInput('pillarHeight', e.target.value)} />
                                <Button size="sm" variant="outline" className="h-7 flex-1 text-[10px]" onClick={() => send("pillar_up", { height: parseInt(inputs.pillarHeight), block: inputs.blockName })}>
                                    <ArrowUp className="w-3 h-3 mr-1" /> Pillar Up
                                </Button>
                            </div>
                            {/* mine down */}
                            <div className="flex gap-1">
                                <Input placeholder="D" className="h-7 w-12 bg-white text-[10px]" value={inputs.mineDepth} onChange={e => updateInput('mineDepth', e.target.value)} />
                                <Button size="sm" variant="outline" className="h-7 flex-1 text-[10px]" onClick={() => send("mine_down", { depth: parseInt(inputs.mineDepth) })}>
                                    <ArrowDown className="w-3 h-3 mr-1" /> Mine Down
                                </Button>
                            </div>
                            {/* bridge */}
                            <div className="flex gap-1">
                                <Input placeholder="#" className="h-7 w-12 bg-white text-[10px]" value={inputs.bridgeCount} onChange={e => updateInput('bridgeCount', e.target.value)} />
                                <select className="h-7 rounded-sm border border-gray-200 text-[10px]" value={inputs.bridgeDir} onChange={e => updateInput('bridgeDir', e.target.value)}>
                                    {bridgeOptions.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                                </select>
                                <Button size="sm" variant="outline" className="h-7 flex-1 text-[10px]" onClick={() => send("bridge", { count: parseInt(inputs.bridgeCount), direction: inputs.bridgeDir })}>
                                    Bridge
                                </Button>
                            </div>
                            <Button size="sm" className="w-full h-7 bg-purple-600 hover:bg-purple-700 text-white text-[10px]"
                                onClick={() => send("bridge", { x: parseFloat(actCoords.x), z: parseFloat(actCoords.z) })}>
                                Bridge To Target
                            </Button>
                        </div>

                        <Separator />

                        {/* basic interaction */}
                        <div className="space-y-2">
                            <Input placeholder="Block Name (e.g. dirt)" className="h-7 bg-white text-xs" value={inputs.blockName} onChange={e => updateInput('blockName', e.target.value)} />
                            <div className="grid grid-cols-2 gap-2">
                                <Button size="sm" variant="outline" className="h-8 border-amber-200 text-amber-700 hover:bg-amber-50"
                                    onClick={() => send("mine_block", { x: parseInt(actCoords.x), y: parseInt(actCoords.y), z: parseInt(actCoords.z) })}>
                                    <Hammer className="w-3 h-3 mr-2" /> Mine
                                </Button>
                                <Button size="sm" variant="outline" className="h-8 border-emerald-200 text-emerald-700 hover:bg-emerald-50"
                                    onClick={() => send("place_block", { x: parseInt(actCoords.x), y: parseInt(actCoords.y), z: parseInt(actCoords.z), block: inputs.blockName })}>
                                    <Box className="w-3 h-3 mr-2" /> Place
                                </Button>
                            </div>
                            <Button size="sm" className="w-full h-7 bg-orange-500 hover:bg-orange-600 text-white text-[10px]" onClick={() => send("use_block", { x: parseInt(actCoords.x), y: parseInt(actCoords.y), z: parseInt(actCoords.z) })}>
                                Use Block (Act Tgt)
                            </Button>
                        </div>

                        {/* crafting */}
                        <div className="space-y-2 bg-amber-50 p-2 rounded-md border border-amber-200">
                            <Label className="text-[10px] text-amber-600 uppercase font-bold flex justify-between items-center">
                                Crafting
                                <span className="text-[9px] font-normal text-amber-400">
                                    {((data.inventory?.context?.craftable_2x2?.length || 0) + (data.inventory?.context?.craftable_3x3?.length || 0))} Avail
                                </span>
                            </Label>

                            <div className="flex flex-col gap-2">
                                <Input
                                    placeholder="Item Name (e.g. stick)"
                                    className="h-7 bg-white text-[10px] w-full border-amber-200 focus-visible:ring-amber-400"
                                    value={inputs.craftItem}
                                    onChange={e => updateInput('craftItem', e.target.value)}
                                />
                                <div className="flex gap-1">
                                    <div className="flex items-center bg-white border border-amber-200 rounded-sm">
                                        <button className="px-2 hover:bg-amber-100 text-amber-600 text-xs" onClick={() => updateInput('craftQty', Math.max(1, parseInt(inputs.craftQty) - 1))}>-</button>
                                        <Input
                                            className="h-7 w-10 text-center border-0 p-0 text-[10px] focus-visible:ring-0"
                                            value={inputs.craftQty}
                                            onChange={e => updateInput('craftQty', e.target.value)}
                                        />
                                        <button className="px-2 hover:bg-amber-100 text-amber-600 text-xs" onClick={() => updateInput('craftQty', parseInt(inputs.craftQty) + 1)}>+</button>
                                    </div>
                                    <Button size="sm" className="h-7 flex-1 bg-amber-500 hover:bg-amber-600 text-white text-[10px]" onClick={() => send("craft_item", { item: inputs.craftItem, quantity: parseInt(inputs.craftQty) })}>
                                        Craft
                                    </Button>
                                </div>
                            </div>

                            {/* quick craft list */}
                            {(data.inventory?.context?.craftable_2x2 || data.inventory?.context?.craftable_3x3) && (
                                <div className="flex flex-wrap gap-1 max-h-24 overflow-y-auto mt-1 pr-1">
                                    {[...(data.inventory?.context?.craftable_2x2 || []), ...(data.inventory?.context?.craftable_3x3 || [])]
                                        .filter((v, i, a) => a.findIndex(t => (t.item === v.item)) === i) // Unique
                                        .slice(0, 15) // Limit
                                        .map((c, i) => (
                                            <div key={i}
                                                className="px-1.5 py-0.5 bg-white border border-amber-100 rounded text-[9px] text-amber-800 cursor-pointer hover:bg-amber-100 truncate max-w-[100px]"
                                                title={`Able to craft ${c.max_craftable}x`}
                                                onClick={() => {
                                                    updateInput('craftItem', c.item.replace("minecraft:", ""));
                                                    updateInput('craftQty', 1); // reset qty or set to max? 1 is safer.
                                                }}
                                            >
                                                {c.item.replace("minecraft:", "")}
                                            </div>
                                        ))}
                                </div>
                            )}
                        </div>

                        <Separator />

                        {/* machines & storage */}
                        <div className="space-y-2 bg-gray-200 p-2 rounded-md">
                            <Label className="text-[10px] text-gray-500 uppercase font-bold">Machine/Container</Label>
                            <div className="flex gap-1">
                                <Input placeholder="In" className="h-6 bg-white text-[10px]" value={inputs.smeltInput} onChange={e => updateInput('smeltInput', e.target.value)} />
                                <Input placeholder="Fuel" className="h-6 bg-white text-[10px]" value={inputs.smeltFuel} onChange={e => updateInput('smeltFuel', e.target.value)} />
                                <Button size="sm" className="h-6 text-[10px] px-2" onClick={() => send("smelt_item", { input_item: inputs.smeltInput, fuel_item: inputs.smeltFuel })}>Smelt</Button>
                            </div>
                            <div className="flex gap-1">
                                <Input placeholder="Item Name" className="h-6 bg-white text-[10px]" value={inputs.storeName} onChange={e => updateInput('storeName', e.target.value)} />
                                <Button size="sm" className="h-6 text-[10px] px-1" onClick={() => send("store_item", { item: inputs.storeName })}>Store</Button>
                                <Button size="sm" className="h-6 text-[10px] px-1" onClick={() => send("retrieve_item", { item: inputs.storeName })}>Get</Button>
                            </div>
                        </div>

                        {/* equip & discard */}
                        <div className="space-y-2 bg-gray-200 p-2 rounded-md">
                            <Label className="text-[10px] text-gray-500 uppercase font-bold">Equip & Discard</Label>
                            <div className="flex gap-1">
                                <Input placeholder="Item" className="h-6 bg-white text-[10px]" value={inputs.equipItem} onChange={e => updateInput('equipItem', e.target.value)} />
                                <select className="h-6 text-[10px] rounded-sm border-gray-300" value={inputs.equipDest} onChange={e => updateInput('equipDest', e.target.value)}>
                                    {equipOptions.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                                </select>
                                <Button size="sm" className="h-6 text-[10px] bg-green-600 text-white" onClick={() => send("equip_item", { item: inputs.equipItem, destination: inputs.equipDest })}>Equip</Button>
                            </div>
                            <div className="flex gap-1">
                                <Input placeholder="Trash Item" className="h-6 bg-white text-[10px]" value={inputs.discardItem} onChange={e => updateInput('discardItem', e.target.value)} />
                                <Button size="sm" className="h-6 text-[10px] bg-red-600 text-white px-1" onClick={() => send("discard_item", { item: inputs.discardItem })}>
                                    <Trash2 className="w-3 h-3" />
                                </Button>
                                <Button size="sm" className="h-6 text-[10px] bg-pink-600 text-white px-1" onClick={() => send("eat_food", {})}>
                                    <Utensils className="w-3 h-3" />
                                </Button>
                            </div>
                        </div>

                        {/* combat */}
                        <div className="space-y-2 p-2 rounded-md border border-red-200 bg-red-50">
                            <Label className="text-[10px] text-red-500 uppercase font-bold">Combat</Label>
                            <div className="flex gap-1">
                                <Input placeholder="Target ID/Name" className="h-7 bg-white text-[10px]" value={inputs.attackTarget} onChange={e => updateInput('attackTarget', e.target.value)} />
                                <Button size="sm" className="h-7 bg-red-600 hover:bg-red-700 text-white" onClick={() => {
                                    const val = inputs.attackTarget;
                                    const target = !isNaN(parseInt(val)) ? parseInt(val) : val;
                                    send("attack_entity", { target });
                                }}>Attack</Button>
                            </div>
                        </div>


                        <Separator />

                        {/* chat & vision */}
                        <div className="pb-10 space-y-2">
                            <Label className="text-xs text-gray-500 uppercase tracking-wider font-bold">Comm</Label>
                            <div className="flex gap-2">
                                <Input placeholder="Say..." className="h-8 bg-white text-xs" value={inputs.chat} onChange={e => updateInput('chat', e.target.value)} />
                                <Button size="sm" className="h-8 px-2" onClick={() => { send("chat", { message: inputs.chat }); updateInput('chat', '') }}>
                                    <MessageSquare className="w-4 h-4" />
                                </Button>
                            </div>
                            <Button variant="secondary" size="sm" className="w-full h-8" onClick={() => send("request_screenshot")}>
                                <Eye className="w-4 h-4 mr-2" /> Update Vision
                            </Button>
                        </div>

                    </div>

                    {/* MAIN CONTENT AREA */}
                    <div className="flex-1 flex flex-col overflow-hidden bg-white">

                        {/* Top Panel: Vision & Logs */}
                        <div className="h-1/2 flex border-b border-gray-200">
                            {/* Vision / World View */}
                            <div className="flex-1 p-4 border-r border-gray-200 flex flex-col">
                                <h3 className="text-sm font-bold text-gray-400 mb-2 flex justify-between">
                                    <span>Agent Vision</span>
                                    <span className="font-mono text-gray-400 text-xs">Latent Space</span>
                                </h3>
                                <div className="flex-1 bg-gray-100 rounded-lg border border-gray-200 flex items-center justify-center relative overflow-hidden group">
                                    {data.screenshot ? (
                                        <img src={`data:image/png;base64,${data.screenshot}`} className="w-full h-full object-contain" />
                                    ) : (
                                        <span className="text-gray-400 text-xs">No Signal</span>
                                    )}
                                </div>
                            </div>

                            {/* console logs */}
                            <div className="w-[450px] p-4 flex flex-col bg-gray-50">
                                <h3 className="text-sm font-bold text-gray-500 mb-2">Systems Log</h3>
                                <ScrollArea className="flex-1 font-mono text-[11px] text-gray-600 bg-white border border-gray-200 rounded p-2">
                                    <div className="space-y-1">
                                        {logs.map((log, i) => (
                                            <div key={i} className="break-words border-b border-gray-100 py-0.5">{log}</div>
                                        ))}
                                    </div>
                                </ScrollArea>
                            </div>
                        </div>

                        {/* Bottom Panel: Stats & Inventory */}
                        <div className="h-1/2 flex p-4 gap-4 overflow-hidden bg-gray-50">

                            {/* Stats Card */}
                            <div className="w-64 space-y-4">
                                <Card className="bg-white border-gray-200 shadow-sm">
                                    <CardContent className="p-4 space-y-2">
                                        <div className="flex justify-between text-xs">
                                            <span className="text-gray-500">Position</span>
                                            <span className="font-mono text-green-600 font-bold">
                                                {data.player ? `${data.player.position.x.toFixed(1)}, ${data.player.position.y.toFixed(1)}, ${data.player.position.z.toFixed(1)}` : 'Unknown'}
                                            </span>
                                        </div>
                                        <div className="flex justify-between text-xs">
                                            <span className="text-gray-500">Health</span>
                                            <span className="font-mono text-red-500 font-bold">
                                                {data.player?.health.toFixed(0) || '0'} / 20
                                            </span>
                                        </div>
                                        <div className="flex justify-between text-xs">
                                            <span className="text-gray-500">Food</span>
                                            <span className="font-mono text-amber-600 font-bold">
                                                {data.player?.food || '0'} / 20
                                            </span>
                                        </div>
                                    </CardContent>
                                </Card>

                                {/* Context List (Context) */}
                                <div className="flex-col gap-2 h-full hidden">
                                    {/* Can add Entity list here if needed, mirroring index.html */}
                                </div>

                                {/* Lidar List */}
                                <div className="flex-1 border border-gray-200 rounded-md p-2 overflow-y-auto bg-white shadow-sm min-h-0">
                                    <div className="text-[10px] font-bold text-gray-500 sticky top-0 bg-white pb-1">SURROUNDINGS</div>
                                    <div className="space-y-0.5">
                                        {data.lidar.blocks.slice(0, 50).map((b, i) => (
                                            <div key={i} className="text-[10px] font-mono text-gray-500 cursor-pointer hover:bg-blue-50 hover:text-blue-600 px-1 rounded"
                                                onClick={() => {
                                                    setMoveCoords({ x: b.x, y: b.y + 1, z: b.z });
                                                    setActCoords({ x: b.x, y: b.y, z: b.z });
                                                }}
                                            >
                                                [{b.x},{b.y},{b.z}] {b.name.replace('minecraft:', '')}
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            </div>

                            {/* inventory */}
                            <div className="flex-1 flex flex-col gap-2">
                                <div className="bg-white p-3 rounded-lg border border-gray-200 shadow-sm">
                                    <Label className="text-xs text-gray-500 mb-2 block uppercase font-bold">Hotbar</Label>
                                    <div className="flex gap-1 justify-center">
                                        {data.inventory?.hotbar.map(slot => renderSlot(slot, true, data.inventory.selected_slot))}
                                    </div>
                                </div>

                                <div className="flex-1 bg-white p-3 rounded-lg border border-gray-200 shadow-sm overflow-y-auto">
                                    <Label className="text-xs text-gray-500 mb-2 block uppercase font-bold">Main Inventory</Label>
                                    <div className="grid grid-cols-9 gap-1 w-fit mx-auto">
                                        {data.inventory?.main.map(slot => renderSlot(slot))}
                                    </div>
                                </div>
                            </div>

                        </div>
                    </div>

                </div>
            </div>
        </div>
    );
}
