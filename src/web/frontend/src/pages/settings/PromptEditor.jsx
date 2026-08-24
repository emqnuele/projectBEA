import React, { useEffect, useRef, useState } from 'react';
import { Bold, Code, Hash, Italic, List } from 'lucide-react';
import { Modal } from '../../components/ui/Modal';
import { Button, IconButton } from '../../components/ui/controls';

const TOOLS = [
    { icon: Bold, label: 'Bold', prefix: '**', suffix: '**' },
    { icon: Italic, label: 'Italic', prefix: '*', suffix: '*' },
    { icon: Hash, label: 'Heading', prefix: '## ' },
    { icon: List, label: 'List item', prefix: '- ' },
    { icon: Code, label: 'Code block', prefix: '```\n', suffix: '\n```' },
];

export function PromptEditor({ open, value, onClose, onSave }) {
    const [text, setText] = useState(value);
    const areaRef = useRef(null);

    useEffect(() => { if (open) setText(value); }, [open, value]);

    const wrap = ({ prefix, suffix = '' }) => {
        const area = areaRef.current;
        if (!area) return;
        const { selectionStart: start, selectionEnd: end, value: content } = area;
        const next = content.slice(0, start) + prefix + content.slice(start, end) + suffix + content.slice(end);
        setText(next);
        requestAnimationFrame(() => {
            area.focus();
            area.setSelectionRange(start + prefix.length, end + prefix.length);
        });
    };

    return (
        <Modal
            open={open}
            onClose={onClose}
            size="xl"
            title="Instructions"
            description={`Markdown · ${text.length} characters · applied when you save the settings`}
            footer={
                <>
                    <Button variant="ghost" onClick={onClose}>Cancel</Button>
                    <Button variant="primary" onClick={() => onSave(text)}>Use these instructions</Button>
                </>
            }
        >
            <div className="-mx-5 -my-4 flex h-[62vh] flex-col">
                <div className="flex items-center gap-0.5 border-b border-line px-3 py-1.5">
                    {TOOLS.map((tool) => (
                        <IconButton key={tool.label} label={tool.label} size="sm" onClick={() => wrap(tool)}>
                            <tool.icon size={13} />
                        </IconButton>
                    ))}
                </div>
                <textarea
                    ref={areaRef}
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                    spellCheck="false"
                    aria-label="Instructions"
                    placeholder="Leave empty to use the defaults."
                    className="bare min-h-0 flex-1 resize-none bg-transparent p-5 font-mono text-[12.5px]
                               leading-relaxed text-text outline-none placeholder:text-faint"
                />
            </div>
        </Modal>
    );
}
