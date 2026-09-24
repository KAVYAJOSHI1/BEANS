import React, { useState } from 'react';
import { Play, Pause, RotateCcw, ArrowRight, Clock, ShieldCheck, ShieldAlert, Cpu } from 'lucide-react';

export default function TimelineReplay({ timelineEvents }) {
  const [currentStep, setCurrentStep] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);

  const events = timelineEvents || [];
  const activeEvent = events[currentStep] || events[0];

  const handleNext = () => {
    setCurrentStep((prev) => (prev < events.length - 1 ? prev + 1 : 0));
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-slate-900">Chronological Transaction Flow & Peel Replay</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Step-by-step investigative replay of fund dissemination, peel chains, and CoinJoin tumbler cycles.
          </p>
        </div>

        {/* Playback Controls */}
        <div className="flex items-center space-x-2">
          <button
            onClick={() => setCurrentStep(0)}
            className="p-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 transition-colors"
            title="Reset to First Hop"
          >
            <RotateCcw className="w-4 h-4" />
          </button>
          <button
            onClick={handleNext}
            className="px-4 py-2 rounded-lg bg-blue-600 text-white font-semibold text-xs shadow-md hover:bg-blue-700 transition-all flex items-center space-x-1.5"
          >
            <span>Next Hop</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Progress Slider */}
      <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm space-y-4">
        <div className="flex justify-between text-xs font-semibold text-slate-600">
          <span>Step {currentStep + 1} of {events.length}</span>
          <span>{activeEvent?.timestamp}</span>
        </div>
        <input
          type="range"
          min="0"
          max={Math.max(0, events.length - 1)}
          value={currentStep}
          onChange={(e) => setCurrentStep(Number(e.target.value))}
          className="w-full accent-blue-600 cursor-pointer"
        />
      </div>

      {/* Active Step Highlight Card */}
      {activeEvent && (
        <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm space-y-4">
          <div className="flex items-center justify-between border-b border-slate-100 pb-3">
            <div className="flex items-center space-x-2">
              <span className="w-7 h-7 rounded-full bg-blue-100 text-blue-700 font-bold flex items-center justify-center text-xs">
                #{activeEvent.step}
              </span>
              <span className="font-mono text-sm font-bold text-slate-900">{activeEvent.txid}</span>
            </div>
            {activeEvent.is_peel && (
              <span className="px-2.5 py-1 rounded bg-rose-50 text-rose-700 border border-rose-200 text-xs font-bold">
                PEEL HOP
              </span>
            )}
            {activeEvent.is_split && (
              <span className="px-2.5 py-1 rounded bg-orange-50 text-orange-700 border border-orange-200 text-xs font-bold">
                RAPID FAN-OUT SPLIT
              </span>
            )}
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
            <div className="p-3 rounded-lg bg-slate-50 border border-slate-100">
              <span className="text-slate-500 font-semibold">Transaction Volume:</span>
              <div className="text-base font-bold text-slate-900 mt-1">{activeEvent.amount_btc} BTC</div>
            </div>
            <div className="p-3 rounded-lg bg-slate-50 border border-slate-100">
              <span className="text-slate-500 font-semibold">Miner Priority Fee:</span>
              <div className="text-base font-bold text-slate-900 mt-1">{activeEvent.fee_btc} BTC</div>
            </div>
            <div className="p-3 rounded-lg bg-slate-50 border border-slate-100">
              <span className="text-slate-500 font-semibold">Relaying IP Node:</span>
              <div className="text-base font-bold font-mono text-slate-900 mt-1">{activeEvent.src_ip}</div>
            </div>
            <div className="p-3 rounded-lg bg-slate-50 border border-slate-100">
              <span className="text-slate-500 font-semibold">Infrastructure / ASN:</span>
              <div className="text-base font-bold text-slate-900 mt-1">{activeEvent.geo_country} · {activeEvent.asn}</div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
