import { Component, input } from '@angular/core';

const KERNELS: [number, number][] = [];
for (let y = 10; y <= 52; y += 5) {
  for (let x = 19 + ((y / 5) % 2) * 2.5; x <= 45; x += 5) {
    const inside = ((x - 32) / 14) ** 2 + ((y - 31) / 23) ** 2 <= 1;
    const face = x > 21 && x < 43 && y > 22 && y < 42;
    if (inside && !face) KERNELS.push([x, y]);
  }
}

@Component({
  selector: 'app-kolba-avatar',
  template: `
    <svg viewBox="0 0 64 64" [attr.width]="size()" [attr.height]="size()" aria-hidden="true" focusable="false">
      <path d="M30 7 C28 3 25 3 23 1 M32 6 C32 3 33 1 34 0 M34 7 C37 3 40 3 42 2" fill="none" stroke="#9c6b2f" stroke-width="1.6" stroke-linecap="round" />
      <path d="M32 5 C44 5 47 18 47 31 C47 45 41 55 32 55 C23 55 17 45 17 31 C17 18 20 5 32 5 Z" fill="#f5c53a" stroke="#c98f0a" stroke-width="1.5" />
      <g fill="#e3a812">
        @for (k of kernels; track $index) {
          <circle [attr.cx]="k[0]" [attr.cy]="k[1]" r="1.8" />
        }
      </g>
      <circle cx="26.5" cy="30" r="3" fill="#1b1f1d" />
      <circle cx="37.5" cy="30" r="3" fill="#1b1f1d" />
      <circle cx="27.5" cy="29" r="1" fill="#ffffff" />
      <circle cx="38.5" cy="29" r="1" fill="#ffffff" />
      <ellipse cx="23.5" cy="36" rx="2.6" ry="1.6" fill="#f08a6b" opacity="0.7" />
      <ellipse cx="40.5" cy="36" rx="2.6" ry="1.6" fill="#f08a6b" opacity="0.7" />
      <path d="M27.5 36 Q32 40.5 36.5 36" fill="none" stroke="#1b1f1d" stroke-width="2" stroke-linecap="round" />
      <path d="M32 60 C20 58 11 47 12 29 C17 40 24 46 32 50 Z" fill="#6f9a2b" stroke="#3a5a00" stroke-width="1" />
      <path d="M32 60 C44 58 53 47 52 29 C47 40 40 46 32 50 Z" fill="#4f7a18" stroke="#3a5a00" stroke-width="1" />
    </svg>
  `,
  styles: `
    :host {
      display: inline-flex;
      line-height: 0;
    }
  `,
})
export class KolbaAvatar {
  readonly size = input(40);
  protected readonly kernels = KERNELS;
}
