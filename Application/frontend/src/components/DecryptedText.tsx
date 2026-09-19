import React, { useEffect, useState, useRef } from 'react';

export interface DecryptedTextProps {
  text: string;
  speed?: number;
  maxIterations?: number;
  characters?: string;
  className?: string;
  encryptedClassName?: string;
  parentClassName?: string;
  animateOn?: 'view' | 'hover';
}

export const DecryptedText: React.FC<DecryptedTextProps> = ({
  text,
  speed = 35,
  maxIterations = 6,
  characters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!#%&*+',
  className = '',
  encryptedClassName = '',
  parentClassName = '',
  animateOn = 'view',
}) => {
  const [displayText, setDisplayText] = useState(text);
  const [isScrambling, setIsScrambling] = useState(false);
  const intervalRef = useRef<any>(null);

  const scramble = () => {
    let iteration = 0;
    clearInterval(intervalRef.current);
    setIsScrambling(true);

    intervalRef.current = setInterval(() => {
      setDisplayText(
        text
          .split('')
          .map((char, index) => {
            if (char === ' ') return ' ';
            if (index < iteration) {
              return text[index];
            }
            return characters[Math.floor(Math.random() * characters.length)];
          })
          .join('')
      );

      if (iteration >= text.length) {
        clearInterval(intervalRef.current);
        setIsScrambling(false);
        setDisplayText(text);
      }

      iteration += 1 / (maxIterations / 2);
    }, speed);
  };

  useEffect(() => {
    if (animateOn === 'view') {
      scramble();
    }
    return () => clearInterval(intervalRef.current);
  }, [text, animateOn]);

  const handleMouseEnter = () => {
    if (animateOn === 'hover') {
      scramble();
    }
  };

  return (
    <span
      className={parentClassName}
      onMouseEnter={handleMouseEnter}
      style={{ display: 'inline-block' }}
    >
      <span className={isScrambling ? encryptedClassName : className}>{displayText}</span>
    </span>
  );
};

export default DecryptedText;
