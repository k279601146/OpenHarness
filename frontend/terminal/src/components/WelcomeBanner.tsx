import React from 'react';
import {Box, Text} from 'ink';

import {useTheme} from '../theme/ThemeContext.js';

const VERSION = '0.1.0';

const LOGO = ['OpenHarness', 'AI agent workspace'];

export type WelcomeAction = {
	command: string;
	label: string;
	detail: string;
	alwaysVisible?: boolean;
};

export type WelcomeSection = {
	title: string;
	actions: WelcomeAction[];
};

const FEATURE_SECTIONS: WelcomeSection[] = [
	{
		title: 'Start',
		actions: [
			{command: '/onboarding', label: 'Quickstart', detail: 'guided setup and first workflow'},
			{command: '/resume', label: 'History', detail: 'continue a saved session'},
			{command: '/provider', label: 'Account', detail: 'switch provider profile'},
			{command: '/model', label: 'Model', detail: 'choose or pin models'},
		],
	},
	{
		title: 'Trust',
		actions: [
			{command: '/privacy-settings', label: 'Privacy', detail: 'local data and storage controls'},
			{command: '/permissions', label: 'Approvals', detail: 'set tool permission mode'},
			{command: '/usage', label: 'Usage', detail: 'token and session estimates'},
			{command: '/export', label: 'Export', detail: 'download the current transcript'},
		],
	},
	{
		title: 'Workflows',
		actions: [
			{command: 'Ctrl+V', label: 'Images', detail: 'attach an image from clipboard', alwaysVisible: true},
			{command: '/voice', label: 'Voice', detail: 'toggle speech-oriented input'},
			{command: '/skills', label: 'Skills', detail: 'browse packaged capabilities'},
			{command: '/agents', label: 'Agents', detail: 'delegate parallel work'},
		],
	},
];

export function buildWelcomeSections(commands: string[] = []): WelcomeSection[] {
	const commandSet = new Set(commands.map(normalizeCommand).filter(Boolean));
	const hasCommandInventory = commandSet.size > 0;

	return FEATURE_SECTIONS.map((section) => ({
		...section,
		actions: section.actions.filter(
			(action) => action.alwaysVisible || !hasCommandInventory || commandSet.has(action.command),
		),
	})).filter((section) => section.actions.length > 0);
}

export function formatWelcomeStatus(status: Record<string, unknown> = {}): string {
	const provider = readableStatusValue(status.provider, 'provider unknown');
	const model = readableStatusValue(status.model, 'model unknown');
	const auth = readableStatusValue(status.auth_status, 'auth unknown');
	const mode = readableStatusValue(status.permission_mode, 'mode default');

	return `${provider} | ${model} | auth=${auth} | ${mode}`;
}

function normalizeCommand(command: string): string {
	const value = command.trim();
	if (!value) {
		return '';
	}
	return value.startsWith('/') ? value : `/${value}`;
}

function readableStatusValue(value: unknown, fallback: string): string {
	if (typeof value !== 'string') {
		return fallback;
	}
	const trimmed = value.trim();
	return trimmed.length > 0 ? trimmed : fallback;
}

export function WelcomeBanner({
	status = {},
	commands = [],
}: {
	status?: Record<string, unknown>;
	commands?: string[];
}): React.JSX.Element {
	const {theme} = useTheme();
	const sections = buildWelcomeSections(commands);

	return (
		<Box flexDirection="column" marginBottom={1}>
			<Text color={theme.colors.primary} bold>
				{LOGO[0]}
			</Text>
			<Text dimColor>
				{LOGO[1]} v{VERSION}
			</Text>
			<Text dimColor>{formatWelcomeStatus(status)}</Text>
			<Text> </Text>
			<Box flexDirection="column" borderStyle="round" borderColor={theme.colors.primary} paddingX={1}>
				<Text color={theme.colors.primary} bold>
					Product cockpit
				</Text>
				{sections.map((section) => (
					<Box key={section.title} flexDirection="column" marginTop={1}>
						<Text color={theme.colors.secondary} bold>
							{section.title}
						</Text>
						{section.actions.map((action) => (
							<Text key={action.command}>
								<Text dimColor>- </Text>
								<Text color={theme.colors.primary}>{action.command}</Text>
								<Text> {action.label}</Text>
								<Text dimColor> - {action.detail}</Text>
							</Text>
						))}
					</Box>
				))}
			</Box>
			<Text dimColor>Type / to browse commands, or start with a goal in plain language.</Text>
		</Box>
	);
}
