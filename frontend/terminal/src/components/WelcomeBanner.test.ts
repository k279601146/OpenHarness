import assert from 'node:assert/strict';
import test from 'node:test';

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
