import React from 'react';
import { HelpCircle, ArrowRight } from 'lucide-react';

interface ClarificationPickerProps {
  prompt?: string;
  options?: string[];
  onSelectOption: (optionText: string) => void;
}

export const ClarificationPicker: React.FC<ClarificationPickerProps> = ({
  prompt,
  options,
  onSelectOption,
}) => {
  if (!options || options.length === 0) return null;

  return (
    <div className="mt-3.5 rounded-lg border border-amber-200 bg-amber-50/70 p-3 text-xs dark:border-amber-900/60 dark:bg-amber-950/30">
      <div className="flex items-center gap-1.5 font-medium text-amber-800 dark:text-amber-300 mb-2">
        <HelpCircle className="h-4 w-4" />
        <span>Backend Clarification Required</span>
      </div>

      {prompt && (
        <p className="text-amber-900/80 dark:text-amber-200/80 mb-2.5 font-normal">
          {prompt}
        </p>
      )}

      <div className="space-y-1.5">
        {options.map((option, idx) => (
          <button
            key={idx}
            onClick={() => onSelectOption(option)}
            className="w-full flex items-center justify-between px-3 py-2 rounded-md bg-white border border-amber-200/80 text-slate-800 hover:bg-amber-100/50 hover:border-amber-300 text-left transition-colors dark:bg-slate-900 dark:border-amber-900/50 dark:text-slate-200 dark:hover:bg-amber-950/50 cursor-pointer group"
          >
            <span className="font-medium text-xs pr-2">{option}</span>
            <ArrowRight className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400 group-hover:translate-x-0.5 transition-transform shrink-0" />
          </button>
        ))}
      </div>
    </div>
  );
};
