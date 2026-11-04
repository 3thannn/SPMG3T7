import { useEffect, useState } from 'react'
import './EventNeedsFields.css'
import type { Session } from '../api'
import { listLayoutOptions } from '../venuesStore'
import {
  ACCESSIBILITY_OPTIONS,
  FACILITY_OPTIONS,
  FREE_TEXT_MAX,
  LAYOUT_OPTIONS,
  NOT_REQUIRED,
  listedNeeds,
  toggleNeed,
  type EventNeeds,
} from '../eventNeeds'

type NeedErrors = Partial<Record<keyof EventNeeds, string>>

type EventNeedsFieldsProps = {
  needs: EventNeeds
  onChange: (key: keyof EventNeeds, value: string) => void
  errors?: NeedErrors
  disabled?: boolean
  /** Given, the layout choices come from the venue catalogue (Week 9); else the standard list. */
  session?: Session
}

/**
 * Week 9 (G7/A7): the catalogue's layouts, standard names first. Until they
 * load, or if they cannot, the standard list, so the form never goes blank.
 */
function useLayoutOptions(session: Session | undefined): readonly string[] {
  const [layouts, setLayouts] = useState<readonly string[]>(LAYOUT_OPTIONS)
  useEffect(() => {
    if (!session) return
    let cancelled = false
    listLayoutOptions(session)
      .then((loaded) => {
        if (!cancelled && loaded.length > 0) setLayouts(loaded)
      })
      .catch(() => {
        // The standard list stays: the server still checks the choice.
      })
    return () => {
      cancelled = true
    }
  }, [session])
  return layouts
}

/** The hint under a field, or its error once there is one. */
function Message({ id, error, hint }: { id: string; error?: string; hint: string }) {
  return error ? (
    <span className="field-error" id={`${id}-error`}>
      {error}
    </span>
  ) : (
    <span className="field-hint" id={`${id}-hint`}>
      {hint}
    </span>
  )
}

type ChoiceGroupProps = {
  id: keyof EventNeeds
  legend: string
  hint: string
  options: readonly string[]
  value: string
  onChange: (value: string) => void
  error?: string
  disabled: boolean
}

/** Tick any of a fixed list, or "None / Not required" instead. */
function ChoiceGroup({ id, legend, hint, options, value, onChange, error, disabled }: ChoiceGroupProps) {
  const chosen = listedNeeds(value)
  return (
    <fieldset
      className={error ? 'field needs-group needs-group-invalid' : 'field needs-group'}
      aria-describedby={error ? `${id}-error` : `${id}-hint`}
    >
      <legend>{legend}</legend>
      <div className="needs-options">
        {[...options, NOT_REQUIRED].map((option) => (
          <label key={option} className="needs-option">
            <input
              type="checkbox"
              checked={chosen.includes(option)}
              onChange={(event) => onChange(toggleNeed(value, option, event.target.checked, options))}
              disabled={disabled}
            />
            {option}
          </label>
        ))}
      </div>
      <Message id={id} error={error} hint={hint} />
    </fieldset>
  )
}

type DescribedNeedProps = {
  id: keyof EventNeeds
  legend: string
  hint: string
  placeholder: string
  value: string
  onChange: (value: string) => void
  error?: string
  disabled: boolean
}

/** Describe the need in words, or tick "None / Not required" instead. */
function DescribedNeed({ id, legend, hint, placeholder, value, onChange, error, disabled }: DescribedNeedProps) {
  const notRequired = value === NOT_REQUIRED
  return (
    <fieldset className="field needs-group">
      <legend id={`${id}-legend`}>{legend}</legend>
      <textarea
        id={id}
        className="needs-text"
        aria-labelledby={`${id}-legend`}
        maxLength={FREE_TEXT_MAX}
        placeholder={notRequired ? '' : placeholder}
        value={notRequired ? '' : value}
        onChange={(event) => onChange(event.target.value)}
        aria-invalid={Boolean(error)}
        aria-describedby={error ? `${id}-error` : `${id}-hint`}
        disabled={disabled || notRequired}
      />
      <div className="needs-options">
        <label className="needs-option">
          <input
            type="checkbox"
            checked={notRequired}
            onChange={(event) => onChange(event.target.checked ? NOT_REQUIRED : '')}
            disabled={disabled}
          />
          {NOT_REQUIRED}
        </label>
      </div>
      <Message id={id} error={error} hint={hint} />
    </fieldset>
  )
}

/**
 * US2.1 (Sprint 3): the five needs an event request must answer to submit.
 *
 * Controlled: the page owns the values and decides when to show errors, so
 * the same fields serve the new-event form and the draft/change-request form.
 */
export default function EventNeedsFields({
  needs,
  onChange,
  errors = {},
  disabled = false,
  session,
}: EventNeedsFieldsProps) {
  const catalogue = useLayoutOptions(session)
  // A saved answer the catalogue no longer lists still shows as chosen.
  const layoutChoices =
    needs.preferredLayout &&
    needs.preferredLayout !== NOT_REQUIRED &&
    !catalogue.includes(needs.preferredLayout)
      ? [...catalogue, needs.preferredLayout]
      : catalogue
  return (
    <>
      <ChoiceGroup
        id="venueRequirements"
        legend="Venue requirements"
        hint="Required when submitting. The facilities the venue must have — choose all that apply."
        options={FACILITY_OPTIONS}
        value={needs.venueRequirements}
        onChange={(value) => onChange('venueRequirements', value)}
        error={errors.venueRequirements}
        disabled={disabled}
      />

      <div className="field">
        <label htmlFor="preferredLayout">Preferred layout</label>
        <select
          id="preferredLayout"
          value={needs.preferredLayout}
          onChange={(event) => onChange('preferredLayout', event.target.value)}
          aria-invalid={Boolean(errors.preferredLayout)}
          aria-describedby={errors.preferredLayout ? 'preferredLayout-error' : 'preferredLayout-hint'}
          disabled={disabled}
        >
          <option value="">Choose a layout…</option>
          {layoutChoices.map((layout) => (
            <option key={layout} value={layout}>
              {layout}
            </option>
          ))}
          <option value={NOT_REQUIRED}>{NOT_REQUIRED}</option>
        </select>
        <Message
          id="preferredLayout"
          error={errors.preferredLayout}
          hint="Required when submitting. How the room should be set up."
        />
      </div>

      <ChoiceGroup
        id="accessibilityNeeds"
        legend="Accessibility needs"
        hint="Required when submitting. Choose all that apply."
        options={ACCESSIBILITY_OPTIONS}
        value={needs.accessibilityNeeds}
        onChange={(value) => onChange('accessibilityNeeds', value)}
        error={errors.accessibilityNeeds}
        disabled={disabled}
      />

      <DescribedNeed
        id="equipmentNeeds"
        legend="Equipment needs"
        hint="Required when submitting. List the equipment the event needs."
        placeholder="e.g. 2 wireless microphones, 1 clicker"
        value={needs.equipmentNeeds}
        onChange={(value) => onChange('equipmentNeeds', value)}
        error={errors.equipmentNeeds}
        disabled={disabled}
      />

      <DescribedNeed
        id="registrationNeeds"
        legend="Registration needs"
        hint="Required when submitting. How attendees sign up or check in."
        placeholder="e.g. Online sign-up closing a week before; check-in desk at the door"
        value={needs.registrationNeeds}
        onChange={(value) => onChange('registrationNeeds', value)}
        error={errors.registrationNeeds}
        disabled={disabled}
      />
    </>
  )
}
