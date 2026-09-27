import React from 'react';

export function Pill({ children, icon: Icon, className = '' }) {
  return <span className={`pill ${className}`}>{Icon ? <Icon size={14} /> : null}{children}</span>;
}

export function SectionHeading({ eyebrow, title, note, action }) {
  return <div className="section-heading"><div><div className="eyebrow">{eyebrow}</div><h2>{title}</h2>{note ? <p>{note}</p> : null}</div>{action}</div>;
}
