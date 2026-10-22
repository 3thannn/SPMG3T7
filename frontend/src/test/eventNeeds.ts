import { NOT_REQUIRED, type EventNeeds } from '../eventNeeds'

/**
 * US2.1 (Sprint 3): every need answered, so a fixture event can be submitted.
 * Mixes fixed-list choices with a free-text answer and a "None / Not required".
 */
export const ANSWERED_NEEDS: EventNeeds = {
  venueRequirements: 'Stage, Projector',
  preferredLayout: 'Theatre',
  accessibilityNeeds: 'Wheelchair access',
  equipmentNeeds: 'Two wireless microphones',
  registrationNeeds: NOT_REQUIRED,
}
