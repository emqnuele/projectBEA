import React from 'react';
import { motion } from 'framer-motion';
import { Activity, ArrowRight } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

const LandingPage = () => {
    const navigate = useNavigate();

    return (
        <div className="relative min-h-screen w-full bg-slate-50 text-slate-900 overflow-hidden font-sans selection:bg-cyan-100 flex flex-col items-center justify-center">

            {/* --- ambient background --- */}
            <div className="fixed inset-0 z-0 overflow-hidden pointer-events-none">
                {/* main gradient mesh */}
                <div className="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] bg-blue-100/60 rounded-full blur-[120px] mix-blend-multiply opacity-70 animate-blob" />
                <div className="absolute top-[-10%] right-[-10%] w-[50%] h-[50%] bg-emerald-100/60 rounded-full blur-[120px] mix-blend-multiply opacity-70 animate-blob animation-delay-2000" />
                <div className="absolute bottom-[-20%] left-[20%] w-[50%] h-[50%] bg-purple-100/60 rounded-full blur-[120px] mix-blend-multiply opacity-70 animate-blob animation-delay-4000" />

                {/* noise/grain overlay */}
                <div className="absolute inset-0 opacity-[0.015] bg-[url('https://grainy-gradients.vercel.app/noise.svg')]" />
            </div>

            {/* --- main content --- */}
            <div className="relative z-10 flex flex-col items-center justify-center w-full max-w-4xl px-4">

                {/* glass card container */}
                <motion.div
                    initial={{ opacity: 0, y: 30, scale: 0.98 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
                    className="relative bg-white/40 backdrop-blur-2xl border border-white/60 shadow-[0_8px_32px_0_rgba(31,38,135,0.07)] rounded-[2rem] p-12 md:p-16 flex flex-col items-center text-center w-full max-w-xl mx-auto"
                >
                    {/* status pill */}
                    <motion.div
                        initial={{ opacity: 0, y: -10 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.3, duration: 0.5 }}
                        className="mb-8 px-4 py-1.5 bg-white/60 border border-white/50 backdrop-blur-md rounded-full flex items-center gap-2.5 shadow-sm"
                    >
                        <div className="relative flex items-center justify-center w-2.5 h-2.5">
                            <span className="absolute inline-flex w-full h-full rounded-full bg-emerald-400 opacity-75 animate-ping"></span>
                            <span className="relative inline-flex rounded-full w-2 h-2 bg-emerald-500"></span>
                        </div>
                        <span className="text-[11px] font-bold tracking-widest text-slate-500 uppercase">System Online</span>
                    </motion.div>

                    {/* logo / title */}
                    <motion.div
                        initial={{ opacity: 0, scale: 0.9 }}
                        animate={{ opacity: 1, scale: 1 }}
                        transition={{ delay: 0.4, duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
                        className="mb-6"
                    >
                        <h1 className="text-5xl md:text-7xl font-sans font-bold tracking-tighter text-slate-900 mb-2 drop-shadow-sm">
                            Project<span className="text-transparent bg-clip-text bg-gradient-to-br from-blue-600 to-emerald-500">Bea</span>
                        </h1>
                        <p className="text-sm md:text-base font-medium text-slate-500 tracking-widest uppercase opacity-80">
                            Neural Engine Interface
                        </p>
                    </motion.div>

                    {/* separator */}
                    <motion.div
                        initial={{ scaleX: 0 }}
                        animate={{ scaleX: 1 }}
                        transition={{ delay: 0.6, duration: 0.8 }}
                        className="w-16 h-[2px] bg-gradient-to-r from-transparent via-slate-200 to-transparent mb-10"
                    />

                    {/* cta button */}
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.7, duration: 0.6 }}
                    >
                        <button
                            onClick={() => navigate('/dashboard')}
                            className="group relative flex items-center gap-3 px-8 py-3.5 bg-white rounded-full shadow-[0_4px_14px_0_rgba(0,0,0,0.05)] hover:shadow-[0_6px_20px_rgba(0,118,255,0.15)] border border-slate-100 transition-all duration-300 transform hover:-translate-y-0.5 active:scale-95"
                        >
                            <span className="text-sm font-semibold tracking-wide text-slate-700 group-hover:text-slate-900 transition-colors">Start</span>
                            <div className="w-8 h-8 rounded-full bg-slate-50 border border-slate-100 flex items-center justify-center group-hover:bg-blue-50 group-hover:border-blue-100 transition-colors duration-300">
                                <ArrowRight className="w-4 h-4 text-slate-400 group-hover:text-blue-500 transition-colors" />
                            </div>
                        </button>
                    </motion.div>

                </motion.div>

                {/* footer info */}
                <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 1, duration: 1 }}
                    className="absolute bottom-[-60px] md:bottom-[-80px] text-xs font-semibold text-slate-400 tracking-widest uppercase opacity-50"
                >
                    V1.0.0
                </motion.div>
            </div>
        </div>
    );
};

export default LandingPage;
