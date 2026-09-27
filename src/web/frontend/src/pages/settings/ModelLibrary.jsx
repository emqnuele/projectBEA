import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AlertTriangle, Download, Eye, Loader2, Plus, Trash2, Upload } from 'lucide-react';
import { api } from '../../api';
import { cn } from '../../lib/cn';
import { Button, IconButton } from '../../components/ui/controls';
import { useToast } from '../../state/ToastProvider';
import { Group } from './parts';

/**
 * The models on this machine, the free ones that can be fetched, and the clips.
 *
 * Choosing a model is saved by the engine on its own and swaps only the body on
 * stage; the page's copy of the settings adopts it so a later save cannot undo it.
 */

const mb = (bytes) => `${(bytes / 1e6).toFixed(bytes < 1e7 ? 1 : 0)} MB`;

// what a vrm's licence fields allow, in the words someone streaming needs
function terms(licence) {
    if (!licence) return [];
    const out = [];
    const commercial = ['corporation', 'personalProfit', 'Allow'].includes(licence.commercial);
    out.push({ text: commercial ? 'Commercial use' : 'Non-commercial', warn: !commercial });
    if (licence.redistribution === true) out.push({ text: 'Redistributable' });
    if (licence.credit_required) out.push({ text: 'Credit required', warn: true });
    return out;
}

function Terms({ items }) {
    if (!items.length) return null;
    return (
        <ul className="flex flex-wrap gap-1">
            {items.map((t) => (
                <li
                    key={t.text}
                    className={cn('rounded-full border px-2 py-0.5 text-[10px] leading-tight',
                        t.warn ? 'text-text' : 'border-line text-dim')}
                    style={t.warn ? { borderColor: 'color-mix(in srgb, var(--vital) 40%, transparent)' } : undefined}
                >
                    {t.text}
                </li>
            ))}
        </ul>
    );
}

function Portrait({ model }) {
    const [broken, setBroken] = useState(false);
    if (!model.has_thumbnail || broken) {
        return (
            <div className="grid h-full w-full place-items-center bg-fill-2 font-display text-3xl text-faint">
                {(model.name || '?').slice(0, 1)}
            </div>
        );
    }
    return (
        <img
            src={`/stage/library/models/${encodeURIComponent(model.id)}/thumbnail?v=${model.version}`}
            alt=""
            loading="lazy"
            onError={() => setBroken(true)}
            className="h-full w-full object-cover object-top"
        />
    );
}

function ModelCard({ model, busy, onUse, onPreview, onDelete, previewing }) {
    const [confirming, setConfirming] = useState(false);
    const canDelete = !model.active && !model.external;
    return (
        <li
            className={cn('flex flex-col overflow-hidden rounded-b2 border bg-fill transition-colors',
                model.active ? 'border-transparent' : 'border-line')}
            style={model.active ? { boxShadow: 'inset 0 0 0 1.5px var(--vital)' } : undefined}
        >
            <div className="relative aspect-[3/4] w-full overflow-hidden">
                <Portrait model={model} />
                {model.active && (
                    <span
                        className="absolute left-2 top-2 rounded-full px-2 py-0.5 text-[10px] font-semibold text-text"
                        style={{ background: 'var(--vital-soft)', backdropFilter: 'blur(6px)' }}
                    >
                        On stage
                    </span>
                )}
            </div>
            <div className="flex flex-1 flex-col gap-2 p-3">
                <div className="min-w-0">
                    <p className="truncate text-[13px] font-semibold text-text" title={model.name}>{model.name}</p>
                    <p className="truncate text-[11px] text-faint" title={model.file}>
                        {model.authors?.length ? `${model.authors.join(', ')}, ` : ''}
                        {model.vrm ? `VRM ${model.vrm}` : 'not a VRM'}, {mb(model.size)}
                        {model.external ? ', outside the library' : ''}
                    </p>
                </div>
                <Terms items={terms(model.licence)} />
                {model.credit && <p className="text-[11px] leading-snug text-dim">Credit on stream: {model.credit}</p>}
                {model.warnings?.map((w) => (
                    <p key={w} className="flex gap-1.5 text-[11px] leading-snug text-dim">
                        <AlertTriangle size={12} className="mt-0.5 shrink-0" style={{ color: 'var(--flux-err)' }} />
                        {w}
                    </p>
                ))}
                <div className="mt-auto flex items-center gap-1.5 pt-1">
                    {!model.active && (
                        <Button size="sm" variant="primary" loading={busy} disabled={!model.vrm} onClick={() => onUse(model)}>
                            Use
                        </Button>
                    )}
                    <Button size="sm" variant={previewing ? 'vital' : 'outline'} onClick={() => onPreview(model)} disabled={!model.vrm}>
                        <Eye size={13} /> Preview
                    </Button>
                    {canDelete && (confirming ? (
                        <Button size="sm" variant="danger" className="ml-auto" onClick={() => onDelete(model)} onBlur={() => setConfirming(false)}>
                            Delete file
                        </Button>
                    ) : (
                        <IconButton size="sm" label={`Delete ${model.file}`} className="ml-auto" onClick={() => setConfirming(true)}>
                            <Trash2 size={13} />
                        </IconButton>
                    ))}
                </div>
            </div>
        </li>
    );
}

function DropTile({ accept, kind, onUploaded, title, help, compact }) {
    const toast = useToast();
    const input = useRef(null);
    const [over, setOver] = useState(false);
    const [sending, setSending] = useState(null);

    const send = async (file) => {
        if (!file) return;
        const kinds = accept.split(',');
        if (!kinds.some((suffix) => file.name.toLowerCase().endsWith(suffix))) {
            toast.error('That file was not added', `The library takes ${kinds.join(' and ')} files.`);
            return;
        }
        setSending(file.name);
        try {
            const result = await api.libraryUpload(kind, file);
            toast.success(`${result.file} added`);
            onUploaded(result.file);
        } catch (e) {
            toast.error(`${file.name} was not added`, e.message);
        } finally {
            setSending(null);
            if (input.current) input.current.value = '';
        }
    };

    return (
        <label
            onDragOver={(e) => { e.preventDefault(); setOver(true); }}
            onDragLeave={() => setOver(false)}
            onDrop={(e) => { e.preventDefault(); setOver(false); send(e.dataTransfer.files?.[0]); }}
            className={cn(
                'flex cursor-pointer flex-col items-center justify-center gap-2 rounded-b2 border border-dashed p-4 text-center transition-colors',
                'focus-within:border-line-strong',
                compact ? 'min-h-[5.5rem]' : 'min-h-[14rem]',
                over ? 'border-transparent' : 'border-line hover:border-line-strong',
            )}
            style={over ? { background: 'var(--vital-soft)', boxShadow: 'inset 0 0 0 1px var(--vital)' } : undefined}
        >
            <input ref={input} type="file" accept={accept} className="sr-only" onChange={(e) => send(e.target.files?.[0])} />
            {sending
                ? <Loader2 size={18} className="animate-spin text-dim" />
                : (compact ? <Upload size={16} className="text-dim" /> : <Plus size={20} className="text-dim" />)}
            <span className="text-[12px] font-semibold text-text">{sending ? `Adding ${sending}` : title}</span>
            {!sending && <span className="max-w-[16rem] text-[11px] leading-snug text-faint">{help}</span>}
        </label>
    );
}

function CatalogCard({ asset, onDownload }) {
    const job = asset.download;
    const running = job?.state === 'running';
    const share = running && job.total ? job.written / job.total : 0;
    return (
        <li className="flex flex-col gap-2 rounded-b2 border border-line bg-fill p-3">
            <div className="flex items-baseline justify-between gap-2">
                <p className="text-[13px] font-semibold text-text">{asset.name}</p>
                <span className="shrink-0 text-[11px] text-faint">{mb(asset.size)}</span>
            </div>
            <p className="text-[11px] leading-snug text-dim">{asset.licence}</p>
            {asset.credit && <p className="text-[11px] leading-snug text-text">You must credit: {asset.credit}</p>}
            {job?.state === 'failed' && (
                <p className="text-[11px] leading-snug" style={{ color: 'var(--flux-err)' }}>{job.error}</p>
            )}
            {running ? (
                <div className="mt-auto space-y-1 pt-1" role="progressbar" aria-valuenow={Math.round(share * 100)} aria-valuemin={0} aria-valuemax={100}>
                    <div className="h-1 overflow-hidden rounded-full bg-fill-3">
                        <div className="h-full rounded-full transition-[width] duration-300" style={{ width: `${share * 100}%`, background: 'var(--vital)' }} />
                    </div>
                    <p className="text-[11px] text-faint">{mb(job.written)} of {mb(job.total)}</p>
                </div>
            ) : (
                <Button size="sm" variant="outline" className="mt-auto self-start" onClick={() => onDownload(asset)}>
                    <Download size={13} /> {job?.state === 'failed' ? 'Try again' : 'Download'}
                </Button>
            )}
        </li>
    );
}

function ClipRow({ clip }) {
    return (
        <li className="flex items-center gap-3 border-b border-line py-2 last:border-b-0">
            <span className="min-w-0 flex-1 truncate font-mono text-[12px] text-text" title={clip.file}>{clip.name}</span>
            <span className="shrink-0 text-[11px] text-faint">
                {clip.error ? 'unreadable'
                    : clip.format === 'mixamo' ? 'Mixamo, retargeted when it plays'
                        : `${clip.duration?.toFixed(1)} s, ${clip.bones} bones${clip.drives_gaze ? ', moves her eyes' : ''}`}
            </span>
            <span
                className={cn('shrink-0 rounded-full border px-2 py-0.5 text-[10px]', clip.role === 'base' ? 'text-text' : 'border-line text-dim')}
                style={clip.role === 'base' ? { borderColor: 'color-mix(in srgb, var(--vital) 40%, transparent)' } : undefined}
            >
                {clip.role === 'base' ? 'Idle motion' : 'Gesture'}
            </span>
        </li>
    );
}

export function ModelLibrary({ stage, adoptSaved, onPreview, previewId, onClipsChanged }) {
    const toast = useToast();
    const [data, setData] = useState(null);
    const [using, setUsing] = useState(null);
    // after "get the free model": the model to put on stage once it has landed, if the stage is still empty
    const wantOnStage = useRef(null);

    const load = useCallback(async () => {
        try {
            setData(await api.library());
        } catch (e) {
            toast.error('Could not read the model library', e.message);
        }
    }, [toast]);

    useEffect(() => { load(); }, [load, stage.models_dir, stage.clips_dir, stage.model_path]);

    const putOnStage = useCallback(async (model) => {
        setUsing(model.id);
        try {
            const { model_path: path } = await api.librarySelect(model.id);
            adoptSaved((prev) => ({ ...prev, stage: { ...(prev.stage || {}), model_path: path } }));
            toast.success(`${model.name} is on stage`);
        } catch (e) {
            toast.error(`${model.name} was not put on stage`, e.message);
        } finally {
            setUsing(null);
        }
    }, [adoptSaved, toast]);

    // poll only while something is downloading, and only while this panel is open
    const running = (data?.catalog || []).some((a) => a.download?.state === 'running');
    useEffect(() => {
        if (!running) return undefined;
        const timer = setInterval(async () => {
            try {
                const jobs = await api.libraryDownloads();
                const stillRunning = Object.values(jobs).some((j) => j.state === 'running');
                if (!stillRunning) {
                    const fresh = await api.library();
                    setData(fresh);
                    const landed = wantOnStage.current && fresh.models.find((m) => m.file === wantOnStage.current);
                    if (landed && !stage.model_path) putOnStage(landed);
                    wantOnStage.current = null;
                    onClipsChanged?.();
                    return;
                }
                setData((prev) => prev && ({
                    ...prev,
                    catalog: prev.catalog.map((a) => (jobs[a.id] ? { ...a, download: jobs[a.id] } : a)),
                }));
            } catch { /* the next tick asks again */ }
        }, 500);
        return () => clearInterval(timer);
    }, [running, stage.model_path, putOnStage, onClipsChanged]);

    const download = async (asset) => {
        try {
            await api.libraryDownload(asset.id);
            await load();
        } catch (e) {
            toast.error(`${asset.name} did not start downloading`, e.message);
        }
    };

    const getDefaults = async () => {
        const defaults = (data?.catalog || []).filter((a) => a.default && !a.installed);
        const model = (data?.catalog || []).find((a) => a.default && a.kind === 'model');
        wantOnStage.current = model?.file || null;
        for (const asset of defaults) await download(asset);
        if (!defaults.length) load();
    };

    const remove = async (model) => {
        try {
            await api.libraryDelete(model.id);
            toast.success(`${model.file} deleted`);
            load();
        } catch (e) {
            toast.error(`${model.file} was not deleted`, e.message);
        }
    };

    if (!data) {
        return (
            <Group title="Models">
                <p className="flex items-center gap-2 text-[12px] text-faint"><Loader2 size={13} className="animate-spin" /> Reading the library</p>
            </Group>
        );
    }

    const free = data.catalog.filter((a) => a.kind === 'model' && !a.installed);
    const defaultModel = data.catalog.find((a) => a.default && a.kind === 'model');
    const defaultsSize = data.catalog.filter((a) => a.default).reduce((sum, a) => sum + a.size, 0);
    const fetchingDefaults = data.catalog.some((a) => a.default && a.download?.state === 'running');

    return (
        <>
            <Group title="Models" description={`The .vrm files in ${data.models_dir}. Choosing one swaps her body on stage without restarting anything.`}>
                {!data.models.length && defaultModel && (
                    <div className="flex flex-wrap items-center gap-3 rounded-b2 border border-line bg-fill p-3">
                        <div className="min-w-0 flex-1">
                            <p className="text-[13px] font-semibold text-text">No model yet</p>
                            <p className="text-[11px] leading-snug text-dim">
                                Get {defaultModel.name} and her idle motion ({mb(defaultsSize)}). {defaultModel.licence}
                            </p>
                        </div>
                        <Button size="sm" variant="primary" loading={fetchingDefaults} onClick={getDefaults}>
                            <Download size={13} /> Get the free model
                        </Button>
                    </div>
                )}
                <ul className="grid grid-cols-2 gap-2.5 sm:grid-cols-3">
                    {data.models.map((model) => (
                        <ModelCard
                            key={model.id}
                            model={model}
                            busy={using === model.id}
                            previewing={previewId === model.id}
                            onUse={putOnStage}
                            onPreview={(m) => onPreview(previewId === m.id ? null : m.id)}
                            onDelete={remove}
                        />
                    ))}
                    <li className="list-none">
                        <DropTile
                            accept=".vrm"
                            kind="models"
                            onUploaded={() => load()}
                            title="Add your own model"
                            help="Drop a .vrm here or choose one. VRoid Studio exports work, 1.0 or 0.x. Its licence is read from the file."
                        />
                    </li>
                </ul>
            </Group>

            {free.length > 0 && (
                <Group title="Free models" description="Pinned to an exact file and checked before they land. The licence is shown before you download.">
                    <ul className="grid gap-2.5 sm:grid-cols-2">
                        {free.map((asset) => <CatalogCard key={asset.id} asset={asset} onDownload={download} />)}
                    </ul>
                </Group>
            )}

            <Group title="Motions" description={`The .vrma clips in ${data.clips_dir}. The idle motion loops under her; a gesture plays when she writes <do:…> or when a mood asks for it.`}>
                {data.clips.length ? (
                    <ul>{data.clips.map((clip) => <ClipRow key={clip.file} clip={clip} />)}</ul>
                ) : (
                    <p className="text-[12px] text-faint">No clips yet. The free model download includes the idle motion.</p>
                )}
                <DropTile
                    compact
                    accept=".vrma,.fbx"
                    kind="clips"
                    onUploaded={() => { load(); onClipsChanged?.(); }}
                    title="Add a motion"
                    help="Drop a .vrma or a Mixamo .fbx. Name it for what it does: the name is what she matches when she picks a gesture."
                />
                <p className="text-[11px] leading-snug text-faint">
                    From <a className="underline hover:text-dim" href="https://www.mixamo.com" target="_blank" rel="noreferrer">Mixamo</a>,
                    download FBX Binary, Without Skin, and keep the file to yourself: Adobe&apos;s terms do not allow sharing it.
                    An idle from Mixamo works as the idle motion too.
                </p>
                <p className="text-[11px] leading-snug text-faint">
                    VRoid&apos;s free motion pack (<a className="underline hover:text-dim" href="https://booth.pm/ja/items/5512385" target="_blank" rel="noreferrer">booth.pm</a>)
                    has seven clips. Its licence does not allow sharing the files, and a stream using them must credit
                    &quot;Character animation credits to pixiv Inc.&apos;s VRoid Project&quot;.
                </p>
            </Group>
        </>
    );
}
