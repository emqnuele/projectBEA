import React, { useState, useEffect, useRef } from 'react';
import { X, Bold, Italic, Hash, Code, List, Save, Type } from 'lucide-react';

export default function SystemPromptModal({ isOpen, onClose, value, onSave }) {
    const [content, setContent] = useState(value || "");
    const [visible, setVisible] = useState(false);
    const [animate, setAnimate] = useState(false);
    const textareaRef = useRef(null);

    useEffect(() => {
        setContent(value || "");
    }, [value, isOpen]);

    useEffect(() => {
        if (isOpen) {
            setVisible(true);
            setTimeout(() => setAnimate(true), 10);
        } else {
            setAnimate(false);
            const timer = setTimeout(() => setVisible(false), 300);
            return () => clearTimeout(timer);
        }
    }, [isOpen]);

    const insertFormat = (prefix, suffix = "") => {
        const textarea = textareaRef.current;
        if (!textarea) return;

        const start = textarea.selectionStart;
        const end = textarea.selectionEnd;
        const text = textarea.value;
        const selected = text.substring(start, end);

        const before = text.substring(0, start);
        const after = text.substring(end);

        const newText = before + prefix + selected + suffix + after;
        setContent(newText);

        // restore focus and selection
        setTimeout(() => {
            textarea.focus();
            textarea.setSelectionRange(start + prefix.length, end + prefix.length);
        }, 0);
    };

    if (!visible) return null;

    return (
        <div className={`fixed inset-0 z-[100] flex items-center justify-center transition-all duration-300 ${animate ? 'backdrop-blur-sm bg-black/40' : 'backdrop-blur-none bg-black/0'}`}>
            <div
                className={`bg-white rounded-xl shadow-2xl w-full max-w-5xl h-[85vh] flex flex-col border border-zinc-200 transform transition-all duration-500 cubic-bezier(0.16, 1, 0.3, 1) ${animate ? 'scale-100 opacity-100 translate-y-0' : 'scale-95 opacity-0 translate-y-8'}`}
            >
                {/* header */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-100">
                    <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-lg bg-zinc-100 flex items-center justify-center text-zinc-600">
                            <Type size={18} />
                        </div>
                        <div>
                            <h3 className="text-lg font-semibold text-zinc-900 leading-none">System Prompt Editor</h3>
                            <p className="text-xs text-zinc-400 mt-1">Markdown Enabled • {content.length} chars</p>
                        </div>
                    </div>
                    <button onClick={onClose} className="p-2 hover:bg-zinc-100 rounded-lg text-zinc-400 hover:text-zinc-900 transition-colors">
                        <X size={20} />
                    </button>
                </div>

                {/* toolbar */}
                <div className="flex items-center gap-1 px-4 py-2 border-b border-zinc-100 bg-zinc-50/50">
                    <ToolbarButton icon={Bold} label="Bold" onClick={() => insertFormat('**', '**')} />
                    <ToolbarButton icon={Italic} label="Italic" onClick={() => insertFormat('*', '*')} />
                    <div className="w-px h-6 bg-zinc-200 mx-1"></div>
                    <ToolbarButton icon={Hash} label="Heading 2" onClick={() => insertFormat('## ')} />
                    <ToolbarButton icon={Code} label="Code Block" onClick={() => insertFormat('```\n', '\n```')} />
                    <ToolbarButton icon={List} label="List" onClick={() => insertFormat('- ')} />
                </div>

                {/* editor area */}
                <div className="flex-1 relative bg-zinc-50/30">
                    <textarea
                        ref={textareaRef}
                        value={content}
                        onChange={(e) => setContent(e.target.value)}
                        className="w-full h-full p-6 resize-none focus:outline-none bg-transparent font-mono text-sm leading-relaxed text-zinc-800"
                        spellCheck="false"
                        placeholder="Enter your system prompt here..."
                    />
                </div>

                {/* footer */}
                <div className="px-6 py-4 border-t border-zinc-100 flex justify-between items-center bg-white rounded-b-xl">
                    <div className="text-xs text-zinc-400">
                        Changes are local until saved.
                    </div>
                    <div className="flex items-center gap-3">
                        <button
                            onClick={onClose}
                            className="px-4 py-2 text-sm font-medium text-zinc-600 hover:text-zinc-900 hover:bg-zinc-100 rounded-lg transition-colors"
                        >
                            Cancel
                        </button>
                        <button
                            onClick={() => onSave(content)}
                            className="flex items-center gap-2 px-6 py-2 text-sm font-medium bg-black text-white hover:bg-zinc-800 rounded-lg transition-colors shadow-sm"
                        >
                            <Save size={16} />
                            Save Changes
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}

function ToolbarButton({ icon: Icon, label, onClick }) {
    return (
        <button
            onClick={onClick}
            title={label}
            className="p-1.5 text-zinc-500 hover:text-zinc-900 hover:bg-white hover:shadow-sm rounded-md transition-all"
        >
            <Icon size={16} />
        </button>
    )
}
