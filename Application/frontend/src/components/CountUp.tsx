import React, { useEffect, useRef, useState } from 'react';

export interface CountUpProps {
  to: number;
  from?: number;
  direction?: 'up' | 'down';
  delay?: number;
  duration?: number;
  className?: string;
  startWhen?: boolean;
  separator?: string;
  decimals?: number;
}

export const CountUp: React.FC<CountUpProps> = ({
  to,
  from = 0,
  delay = 0,
  duration = 1.2,
  className = '',
  startWhen = true,
  separator = '',
  decimals = 0,
}) => {
  const [value, setValue] = useState(from);
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!startWhen) return;

    let startTime: number | null = null;
    let animationFrame: number;
    const startValue = from;
    const endValue = to;

    const timeoutId = setTimeout(() => {
      const step = (timestamp: number) => {
        if (!startTime) startTime = timestamp;
        const progress = Math.min((timestamp - startTime) / (duration * 1000), 1);
        // Exponential ease-out curve
        const easeOut = progress === 1 ? 1 : 1 - Math.pow(2, -10 * progress);
        const current = startValue + (endValue - startValue) * easeOut;
        setValue(current);

        if (progress < 1) {
          animationFrame = requestAnimationFrame(step);
        } else {
          setValue(endValue);
        }
      };

      animationFrame = requestAnimationFrame(step);
    }, delay * 1000);

    return () => {
      clearTimeout(timeoutId);
      cancelAnimationFrame(animationFrame);
    };
  }, [to, from, duration, delay, startWhen]);

  const formatted = decimals > 0 ? value.toFixed(decimals) : Math.round(value).toString();
  const displayValue = separator ? formatted.replace(/\B(?=(\d{3})+(?!\d))/g, separator) : formatted;

  return (
    <span ref={ref} className={`count-up ${className}`}>
      {displayValue}
    </span>
  );
};

export default CountUp;
