import React from 'react';
import { motion } from 'framer-motion';
import { ArrowRight } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

const LandingPage = () => {
    const navigate = useNavigate();

    return (
        <div className="relative min-h-screen w-full bg-white text-zinc-900 overflow-hidden font-sans flex flex-col items-center justify-center select-none">

            {/* --- main content --- */}
            <div className="relative z-10 flex flex-col items-center justify-center w-full max-w-4xl px-4">

                {/* glass card container */}
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.6, ease: "easeOut" }}
                    className="relative bg-zinc-50/50 backdrop-blur-md border border-zinc-200/60 shadow-[0_8px_30px_rgb(0,0,0,0.02)] rounded-[2rem] p-12 md:p-16 flex flex-col items-center text-center w-full max-w-xl mx-auto"
                >
                    {/* logo / title */}
                    <motion.div
                        initial={{ opacity: 0, scale: 0.98 }}
                        animate={{ opacity: 1, scale: 1 }}
                        transition={{ delay: 0.1, duration: 0.6 }}
                        className="mb-6"
                    >
                        <h1 className="text-5xl md:text-6xl font-sans font-bold tracking-tighter text-zinc-950 mb-2">
                            Project<span className="text-zinc-600 font-medium">Bea</span>
                        </h1>
                        <p className="text-xs font-semibold text-zinc-400 tracking-widest uppercase">
                            Neural Engine Interface
                        </p>
                    </motion.div>

                    {/* separator */}
                    <motion.div
                        initial={{ scaleX: 0 }}
                        animate={{ scaleX: 1 }}
                        transition={{ delay: 0.3, duration: 0.6 }}
                        className="w-12 h-[1px] bg-zinc-200 mb-10"
                    />

                    {/* cta button */}
                    <motion.div
                        initial={{ opacity: 0, y: 15 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.4, duration: 0.5 }}
                    >
                        <button
                            onClick={() => navigate('/dashboard')}
                            className="group relative flex items-center gap-3 px-8 py-3.5 bg-black text-white rounded-full shadow-md hover:bg-zinc-800 transition-all duration-300 transform hover:-translate-y-0.5 active:scale-95 cursor-pointer"
                        >
                            <span className="text-sm font-semibold tracking-wide">Start</span>
                            <div className="w-8 h-8 rounded-full bg-white/10 flex items-center justify-center group-hover:bg-white/20 transition-colors duration-300">
                                <ArrowRight className="w-4 h-4 text-white group-hover:text-white transition-colors" />
                            </div>
                        </button>
                    </motion.div>

                </motion.div>

                {/* footer info */}
                <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 0.6, duration: 0.8 }}
                    className="absolute bottom-[-60px] md:bottom-[-80px] text-[10px] font-semibold text-zinc-400 tracking-widest uppercase opacity-80"
                >
                    V1.0.0
                </motion.div>
            </div>
        </div>
    );
};

export default LandingPage;


