import React, { forwardRef } from 'react';
import './Switch.css'; // We'll create this CSS file next

interface SwitchProps extends React.InputHTMLAttributes<HTMLInputElement> {
  checked: boolean;
  onChange: () => void;
}

const Switch = forwardRef<HTMLInputElement, SwitchProps>(
  ({ checked, onChange, ...props }, ref) => {
    return (
      <label className="switch">
        <input
          type="checkbox"
          checked={checked}
          onChange={onChange}
          ref={ref}
          {...props}
        />
        <span className="slider round"></span>
      </label>
    );
  }
);

Switch.displayName = 'Switch';

export default Switch;