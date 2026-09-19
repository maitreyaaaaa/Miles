import React, { useRef } from 'react';
import { motion, useInView } from 'motion/react';

export interface BlurTextProps {
  text?: string;
  delay?: number;
  className?: string;
  animateBy?: 'words' | 'letters';
  direction?: 'top' | 'bottom';
  threshold?: number;
  onAnimationComplete?: () => void;
}

export const BlurText: React.FC<BlurTextProps> = ({
  text = '',
  delay = 60,
  className = '',
  animateBy = 'words',
  direction = 'top',
  threshold = 0.1,
  onAnimationComplete,
}) => {
  const elements = animateBy === 'words' ? text.split(' ') : text.split('');
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, amount: threshold });

  const defaultFrom =
    direction === 'top'
      ? { filter: 'blur(10px)', opacity: 0, transform: 'translate3d(0,-12px,0)' }
      : { filter: 'blur(10px)', opacity: 0, transform: 'translate3d(0,12px,0)' };

  const defaultTo = {
    filter: 'blur(0px)',
    opacity: 1,
    transform: 'translate3d(0,0,0)',
  };

  return (
    <span ref={ref} className={`blur-text ${className}`} style={{ display: 'inline' }}>
      {elements.map((element, i) => (
        <motion.span
          key={i}
          initial={defaultFrom}
          animate={inView ? defaultTo : defaultFrom}
          transition={{
            duration: 0.45,
            delay: (i * delay) / 1000,
            ease: [0.25, 0.1, 0.25, 1],
          }}
          onAnimationComplete={i === elements.length - 1 ? onAnimationComplete : undefined}
          style={{
            display: 'inline-block',
            marginRight: animateBy === 'words' && i < elements.length - 1 ? '0.26em' : undefined,
            willChange: 'transform, filter, opacity',
          }}
        >
          {element === ' ' ? '\u00A0' : element}
        </motion.span>
      ))}
    </span>
  );
};

export default BlurText;
