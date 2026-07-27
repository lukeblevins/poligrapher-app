import { createComponent } from "@lit/react";
import React from "react";

import { MdCheckbox as MdCheckboxElement } from "@material/web/checkbox/checkbox.js";
import { MdFilledButton as MdFilledButtonElement } from "@material/web/button/filled-button.js";
import { MdFilledTonalButton as MdFilledTonalButtonElement } from "@material/web/button/filled-tonal-button.js";
import { MdIconButton as MdIconButtonElement } from "@material/web/iconbutton/icon-button.js";
import { MdOutlinedButton as MdOutlinedButtonElement } from "@material/web/button/outlined-button.js";
import { MdOutlinedTextField as MdOutlinedTextFieldElement } from "@material/web/textfield/outlined-text-field.js";
import { MdFilledTextField as MdFilledTextFieldElement } from "@material/web/textfield/filled-text-field.js";
import { MdRadio as MdRadioElement } from "@material/web/radio/radio.js";
import { MdOutlinedSelect as MdOutlinedSelectElement } from "@material/web/select/outlined-select.js";
import { MdSelectOption as MdSelectOptionElement } from "@material/web/select/select-option.js";
import { MdSwitch as MdSwitchElement } from "@material/web/switch/switch.js";
import { MdTextButton as MdTextButtonElement } from "@material/web/button/text-button.js";
import { MdLinearProgress as MdLinearProgressElement } from "@material/web/progress/linear-progress.js";

type MaterialValueTarget = EventTarget & { value: string };
type MaterialSelectedTarget = EventTarget & { selected: boolean };

export function materialValue(event: Event): string {
  return (event.target as MaterialValueTarget).value;
}

export function materialSelected(event: Event): boolean {
  return (event.target as MaterialSelectedTarget).selected;
}

export const MdFilledButton = createComponent({
  tagName: "md-filled-button",
  elementClass: MdFilledButtonElement,
  react: React,
  events: { onClick: "click" },
});

export const MdFilledTonalButton = createComponent({
  tagName: "md-filled-tonal-button",
  elementClass: MdFilledTonalButtonElement,
  react: React,
  events: { onClick: "click" },
});

export const MdOutlinedButton = createComponent({
  tagName: "md-outlined-button",
  elementClass: MdOutlinedButtonElement,
  react: React,
  events: { onClick: "click" },
});

export const MdTextButton = createComponent({
  tagName: "md-text-button",
  elementClass: MdTextButtonElement,
  react: React,
  events: { onClick: "click" },
});

export const MdIconButton = createComponent({
  tagName: "md-icon-button",
  elementClass: MdIconButtonElement,
  react: React,
  events: { onClick: "click", onChange: "change" },
});

export const MdOutlinedTextField = createComponent({
  tagName: "md-outlined-text-field",
  elementClass: MdOutlinedTextFieldElement,
  react: React,
  events: { onInput: "input", onChange: "change" },
});

export const MdFilledTextField = createComponent({
  tagName: "md-filled-text-field",
  elementClass: MdFilledTextFieldElement,
  react: React,
  events: { onInput: "input", onChange: "change" },
});

export const MdOutlinedSelect = createComponent({
  tagName: "md-outlined-select",
  elementClass: MdOutlinedSelectElement,
  react: React,
  events: { onChange: "change", onInput: "input" },
});

export const MdSelectOption = createComponent({
  tagName: "md-select-option",
  elementClass: MdSelectOptionElement,
  react: React,
});

export const MdSwitch = createComponent({
  tagName: "md-switch",
  elementClass: MdSwitchElement,
  react: React,
  events: { onInput: "input", onChange: "change" },
});

export const MdCheckbox = createComponent({
  tagName: "md-checkbox",
  elementClass: MdCheckboxElement,
  react: React,
  events: { onInput: "input", onChange: "change" },
});

export const MdRadio = createComponent({
  tagName: "md-radio",
  elementClass: MdRadioElement,
  react: React,
  events: { onInput: "input", onChange: "change" },
});

export const MdLinearProgress = createComponent({
  tagName: "md-linear-progress",
  elementClass: MdLinearProgressElement,
  react: React,
});
