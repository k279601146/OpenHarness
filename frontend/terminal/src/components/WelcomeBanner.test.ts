import assert from 'node:assert/strict';
import test from 'node:test';

import {buildCommercialReadiness} from './CommercialReadinessPanel.js';
import {buildWelcomeSections, formatWelcomeStatus} from './WelcomeBanner.js';

function commandsFromSections(commands: string[]): string[] {
	return buildWelcomeSections(commands).flatMap((section) => section.actions.map((action) => action.command));
}

test('shows the full product cockpit before the backend command inventory arrives', () => {
	const commands = commandsFromSections([]);

	assert.ok(commands.includes('/onboarding'));
	assert.ok(commands.includes('/privacy-settings'));
	assert.ok(commands.includes('/agents'));
	assert.ok(commands.includes('Ctrl+V'));
});

test('filters slash actions to the backend command inventory while keeping local shortcuts', () => {
	const commands = commandsFromSections(['/resume', '/privacy-settings', '/voice']);

	assert.deepEqual(commands, ['/resume', '/privacy-settings', 'Ctrl+V', '/voice']);
});

test('formats the runtime status summary for the welcome cockpit', () => {
	assert.equal(
		formatWelcomeStatus({
			provider: 'codex',
			model: 'gpt-5.4',
			auth_status: 'configured',
			permission_mode: 'plan',
		}),
		'codex | gpt-5.4 | auth=configured | plan',
	);
});

test('commercial readiness prioritizes account setup when auth is missing', () => {
	const readiness = buildCommercialReadiness(
		{
			provider: 'anthropic',
			auth_status: 'missing',
			active_profile: 'claude-api',
			profile_label: 'Claude API',
			model: 'claude-sonnet-4-5',
		},
		['/provider', '/login', '/usage'],
	);

	assert.equal(readiness.rows[0]?.value, 'missing');
	assert.deepEqual(readiness.actions.map((action) => action.command), ['/provider', '/login']);
});

test('commercial readiness summarizes usage and pinned models for configured accounts', () => {
	const readiness = buildCommercialReadiness(
		{
			provider: 'codex',
			auth_status: 'configured',
			active_profile: 'codex',
			profile_label: 'Codex Subscription',
			model: 'gpt-5.4',
			allowed_models: ['gpt-5.4', 'gpt-5', 'o4-mini', 'gpt-4.1'],
			input_tokens: 2100,
			output_tokens: 450,
			estimated_tokens: 3000,
			permission_mode: 'Default',
		},
		['/usage', '/rate-limit-options', '/model', '/privacy-settings'],
	);

	assert.equal(readiness.statusLine, 'codex account ready for commercial workflows');
	assert.equal(readiness.rows.find((row) => row.label === 'Model')?.value, 'gpt-5.4 (gpt-5.4, gpt-5, o4-mini +1)');
	assert.equal(readiness.rows.find((row) => row.label === 'Usage')?.value, '2.1k in / 450 out');
	assert.deepEqual(
		readiness.actions.map((action) => action.command),
		['/usage', '/rate-limit-options', '/model', '/privacy-settings'],
	);
});
