// Runs in the browser: it is a form somebody types into.
'use client';

/**
 * The controls a module declares, drawn from the same schema the backend validates with.
 *
 * `backend/registry.py` range-checks every one of these fields on arrival, and the bounds
 * it enforces are the bounds rendered here — the `min`, `max` and option list on each
 * control come from the exported schema, not from a copy in this file. A field the form
 * lets someone fill in but the service will reject is a small dishonesty that costs a
 * round trip and a confusing error, so the two are the same declaration.
 *
 * Client validation is a convenience, never the guarantee. The service revalidates
 * everything; nothing here is trusted downstream.
 *
 * PLAIN ENGLISH -- what this whole file is about:
 *
 * THE FORM. And two rules that look similar and are opposites.
 *
 * RULE 1: THE FORM AND THE CHECKING COME FROM ONE DESCRIPTION.
 * The earliest date the box will accept is the same earliest date the server enforces --
 * because both read the same declaration. Not two lists that agree today.
 * The docstring names the harm precisely: a form that lets you fill in something the
 * service will reject is "a small dishonesty that costs a round trip and a confusing
 * error". You type it, you wait, and you get told off for something the form invited.
 *
 * RULE 2, WHICH SOUNDS LIKE A CONTRADICTION AND IS NOT:
 *
 *     "Client validation is a convenience, never the guarantee."
 *
 * The checking in the browser exists to be HELPFUL -- to catch a mistake before you wait.
 * It is not a security measure and must never be treated as one. Anybody can bypass a
 * browser entirely and send whatever they like.
 * So the server checks everything again, from scratch, trusting nothing that arrives.
 * The two rules together: the form should never mislead you, AND the form should never be
 * relied upon.
 */
import { useState } from 'react';

import type { InputSpec } from '@/lib/runTypes';

export type Values = Record<string, unknown>;

export function Controls({
  inputs,
  values,
  onChange,
  disabled,
  idPrefix,
}: {
  inputs: InputSpec[];
  values: Values;
  onChange: (name: string, value: unknown) => void;
  disabled: boolean;
  idPrefix: string;
}) {
  if (inputs.length === 0) {
    // NO SETTINGS. Says what will happen instead, rather than showing an empty box that
    // would leave a reader wondering whether something failed to load.
    return (
      <p className="small muted">
        This module takes no parameters: it runs over the whole of its declared input.
      </p>
    );
  }
  return (
    <div className="runControls">
      {/* THE FORM IS BUILT FROM THE DECLARATION. No field is written by hand here, which is
          what makes rule 1 structural rather than a promise. */}
      {inputs.map((spec) => (
        <Field
          key={spec.name}
          spec={spec}
          value={values[spec.name]}
          onChange={onChange}
          disabled={disabled}
          // A unique id per field, prefixed so two run panels on one page cannot collide.
          id={`${idPrefix}-${spec.name}`}
        />
      ))}
    </div>
  );
}

// One labelled field.
function Field({
  spec,
  value,
  onChange,
  disabled,
  id,
}: {
  spec: InputSpec;
  value: unknown;
  onChange: (name: string, value: unknown) => void;
  disabled: boolean;
  id: string;
}) {
  const described = spec.note ? `${id}-note` : undefined;
  return (
    <div className="runControls__field">
      {/* `htmlFor` ties the label to its input, so clicking the label focuses the box and
          screen-reader software announces the two together. */}
      <label className="runControls__label" htmlFor={id}>
        {spec.label}
        {/* The required asterisk is hidden from screen readers, because the input itself
            carries the requirement properly -- hearing "star" would only add noise. */}
        {spec.required ? <span aria-hidden="true"> *</span> : null}
      </label>
      <Input
        spec={spec}
        value={value}
        onChange={onChange}
        disabled={disabled}
        id={id}
        describedBy={described}
      />
      {spec.note ? (
        // The hint, formally linked to the input by `aria-describedby` below -- so it is
        // read out as part of the field rather than being loose text a listener may miss.
        <p className="runControls__note" id={described}>
          {spec.note}
        </p>
      ) : null}
    </div>
  );
}

// The right kind of control for each kind of setting.
function Input({
  spec,
  value,
  onChange,
  disabled,
  id,
  describedBy,
}: {
  spec: InputSpec;
  value: unknown;
  onChange: (name: string, value: unknown) => void;
  disabled: boolean;
  id: string;
  describedBy?: string;
}) {
  // The properties every control shares, written once.
  const common = { id, disabled, 'aria-describedby': describedBy } as const;

  switch (spec.kind) {
    case 'date':
      return (
        <input
          {...common}
          // The browser's own date picker -- so it works properly on a phone and in every
          // language, rather than a hand-built calendar that would work in neither.
          type="date"
          value={typeof value === 'string' ? value : ''}
          // THE BOUNDS FROM THE DECLARATION -- rule 1, in two lines. The date picker itself
          // will not let you choose outside the range the server enforces.
          min={typeof spec.minimum === 'string' ? spec.minimum : undefined}
          max={typeof spec.maximum === 'string' ? spec.maximum : undefined}
          onChange={(e) => onChange(spec.name, e.target.value)}
        />
      );

    case 'int':
    case 'float':
      return (
        <input
          {...common}
          type="number"
          // `inputMode` decides which keyboard a phone shows: a plain number pad for whole
          // numbers, one with a decimal point for fractions.
          inputMode={spec.kind === 'int' ? 'numeric' : 'decimal'}
          // Whole numbers step by one; decimals accept anything.
          step={spec.kind === 'int' ? 1 : 'any'}
          value={typeof value === 'number' || typeof value === 'string' ? String(value) : ''}
          min={typeof spec.minimum === 'number' ? spec.minimum : undefined}
          max={typeof spec.maximum === 'number' ? spec.maximum : undefined}
          onChange={(e) =>
            // An empty box stays empty rather than becoming the number 0 -- which would be
            // a value deliberately supplied, and quite different from a field left blank.
            onChange(spec.name, e.target.value === '' ? '' : Number(e.target.value))
          }
        />
      );

    case 'bool':
      return (
        <span className="runControls__switch">
          <input
            {...common}
            type="checkbox"
            // `value === true` rather than a looser test, so an undefined value shows as
            // unchecked rather than as something ambiguous.
            checked={value === true}
            onChange={(e) => onChange(spec.name, e.target.checked)}
          />
        </span>
      );

    case 'select':
      return (
        <select
          {...common}
          value={typeof value === 'string' ? value : ''}
          onChange={(e) => onChange(spec.name, e.target.value)}
        >
          {/* THE OPTIONS FROM THE DECLARATION -- so the list offered is exactly the list
              accepted. */}
          {spec.options.map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
      );

    case 'multiselect':
      return (
        <div className="runControls__checks" id={id} aria-describedby={describedBy}>
          {spec.options.map((o) => {
            const list = Array.isArray(value) ? (value as string[]) : [];
            return (
              <label key={o} className="runControls__check">
                <input
                  type="checkbox"
                  disabled={disabled}
                  checked={list.includes(o)}
                  onChange={(e) =>
                    onChange(
                      spec.name,
                      // Add on tick, remove on untick. `[...list, o]` builds a NEW list
                      // rather than modifying the old one -- which is what lets the page
                      // notice the change and redraw.
                      e.target.checked ? [...list, o] : list.filter((v) => v !== o),
                    )
                  }
                />
                <span>{o}</span>
              </label>
            );
          })}
        </div>
      );

    case 'symbols':
      return (
        <input
          {...common}
          type="text"
          // Both switched off: browser suggestions and spell-check would only interfere with
          // typing share symbols, which are not words.
          autoComplete="off"
          spellCheck={false}
          // The placeholder says what happens if you leave it empty -- so a blank field is
          // an understood choice rather than an omission.
          placeholder="all instruments"
          value={Array.isArray(value) ? (value as string[]).join(', ') : String(value ?? '')}
          onChange={(e) =>
            onChange(
              spec.name,
              e.target.value
                // Split on commas...
                .split(',')
                // ...trim the spaces and upper-case each, so "tcs , infy" works as typed...
                .map((s) => s.trim().toUpperCase())
                // ...and drop the empties, so a trailing comma is harmless.
                .filter(Boolean),
            )
          }
        />
      );

    case 'text':
      return (
        <textarea
          {...common}
          rows={4}
          value={typeof value === 'string' ? value : ''}
          onChange={(e) => onChange(spec.name, e.target.value)}
        />
      );

    case 'document':
      return (
        <DocumentField
          spec={spec}
          value={typeof value === 'string' ? value : ''}
          onChange={onChange}
          disabled={disabled}
          id={id}
          describedBy={describedBy}
        />
      );

    default:
      return (
        // AN UNKNOWN KIND SAYS SO. Not a blank space, and not a guess at a text box -- which
        // would silently send the wrong shape of value. A visible, explicable gap.
        <p className="small muted">
          This build does not know how to render a {spec.kind} control.
        </p>
      );
  }
}


/**
 * A text box with a file picker beside it.
 *
 * The file is sent to the service, which validates its type, size and encoding and sends
 * back the text; the text then travels as an ordinary parameter and is validated again
 * with everything else. Nothing is stored at either end, and this component never reads
 * the file itself — a second decoder here would be a second set of limits to disagree
 * with the first.
 */
// PLAIN ENGLISH: the browser could easily read the file itself -- it is capable of it and
// it would be faster. It deliberately does not.
// Why? Because then there would be TWO pieces of code deciding what counts as an acceptable
// file: one here and one on the server. They would agree at first. Then somebody would
// change one, and the browser would accept a file the server refused -- or worse, the other
// way round.
// Sending the file to the one place that already has those rules means there is only ever
// one answer. And "nothing is stored at either end" is stated plainly, because somebody
// uploading a document deserves to know what happens to it.
function DocumentField({
  spec,
  value,
  onChange,
  disabled,
  id,
  describedBy,
}: {
  spec: InputSpec;
  value: string;
  onChange: (name: string, value: unknown) => void;
  disabled: boolean;
  id: string;
  describedBy?: string;
}) {
  const [status, setStatus] = useState<string>('');
  const [busy, setBusy] = useState(false);

  async function upload(file: File) {
    setBusy(true);
    // Immediate feedback naming the file, so a large one does not look like nothing
    // happening.
    setStatus(`Reading ${file.name}…`);
    const form = new FormData();
    form.append('file', file);
    try {
      const res = await fetch('/api/aegis/uploads/text', { method: 'POST', body: form });
      const payload = (await res.json()) as {
        text?: string;
        filename?: string;
        characters?: number;
        truncated?: boolean;
        error?: { reason: string; remedy: string };
      };
      if (!res.ok || payload.error) {
        // The server's own reason AND remedy shown together -- so a refused file explains
        // both what was wrong and what to do.
        setStatus(
          payload.error ? `${payload.error.reason}. ${payload.error.remedy}` : 'Not read.',
        );
        return;
      }
      onChange(spec.name, payload.text ?? '');
      setStatus(
        // A THOROUGH CONFIRMATION: which file, how many characters, whether it was cut
        // short, and -- crucially -- that nothing was stored. Four facts, one sentence.
        `${payload.filename ?? 'document'}: ${payload.characters ?? 0} characters loaded` +
          (payload.truncated ? ', truncated to the extractor’s ceiling' : '') +
          '. Nothing was stored.',
      );
    } catch {
      // And a fallback that offers a way forward rather than only reporting failure.
      setStatus('The document could not be read. Paste the text instead.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="runControls__document">
      <textarea
        id={id}
        aria-describedby={describedBy}
        // Disabled while a file is being read, so the text cannot be edited underneath an
        // upload that is about to replace it.
        disabled={disabled || busy}
        rows={5}
        // The placeholder offers BOTH routes, so nobody has to hunt for the alternative.
        placeholder="paste text here, or choose a plain-text file"
        value={value}
        onChange={(e) => onChange(spec.name, e.target.value)}
      />
      <div className="runControls__documentRow">
        <input
          type="file"
          // Plain-text formats only. A convenience for the picker, not a security measure --
          // the server checks the type properly regardless of what this suggests.
          accept=".txt,.md,.csv,.text,.log,text/plain"
          disabled={disabled || busy}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void upload(file);
            // Clearing the picker means choosing the SAME file again still triggers a read.
            // Without this line, re-selecting an unchanged file would appear to do nothing.
            e.target.value = '';
          }}
        />
        {value ? (
          <button
            type="button"
            className="runPanel__reset"
            disabled={disabled || busy}
            onClick={() => {
              onChange(spec.name, '');
              setStatus('');
            }}
          >
            Clear text
          </button>
        ) : null}
      </div>
      {status ? <p className="runControls__note">{status}</p> : null}
    </div>
  );
}
