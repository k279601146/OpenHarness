import React from 'react';
import {Box, Text} from 'ink';

import {useTheme} from '../theme/ThemeContext.js';

type ReadinessTone = 'ok' | 'warn' | 'neutral';

export type ReadinessRow = {
	label: string;
	value: string;
	tone?: ReadinessTone;
};

export type ReadinessAction = {
	command: string;
	label: string;
};

export type CommercialReadinessSummary = {
	statusLine: string;
	rows: ReadinessRow[];
	actions: ReadinessAction[];
	footnote: string;
};

const COMMAND_DETAILS: ReadinessAction[] = [
	{command: '/provider', label: 'choose account profile'},
	{command: '/login', label: 'connect external auth'},
	{command: '/model', label: 'pin model choices'},
	{command: '/usage', label: 'inspect token usage'},
	{command: '/rate-limit-options', label: 'reduce provider pressure'},
	{command: '/privacy-settings', label: 'review data controls'},
];

export function buildCommercialReadiness(
	status: Record<string, unknown> = {},
	commands: string[] = [],
): CommercialReadinessSummary {
	const commandSet = new Set(commands.map(normalizeCommand).filter(Boolean));
	const hasCommandInventory = commandSet.size > 0;
	const commandAvailable = (command: string): boolean =>
		!hasCommandInventory || commandSet.has(normalizeCommand(command));

	const auth = readableStatusValue(status.auth_status, 'unknown');
	const authReady = isConfiguredAuth(auth);
	const provider = readableStatusValue(status.provider, 'unknown provider');
	const activeProfile = readableStatusValue(status.active_profile, 'unknown profile');
	const profileLabel = readableStatusValue(status.profile_label, activeProfile);
	const model = readableStatusValue(status.model, 'unknown model');
	const permissionMode = readableStatusValue(status.permission_mode, 'default');
	const inputTokens = readableNumber(status.input_tokens);
	const outputTokens = readableNumber(status.output_tokens);
	const estimatedTokens = readableNumber(status.estimated_tokens);
	const allowedModels = readableStringList(status.allowed_models);
	const totalActualTokens = inputTokens + outputTokens;

	const statusLine = authReady
		? `${provider} account ready for commercial workflows`
		: `${provider} needs account readiness before serious work`;

	const rows: ReadinessRow[] = [
		{label: 'Account', value: auth, tone: authReady ? 'ok' : 'warn'},
		{label: 'Profile', value: formatProfile(activeProfile, profileLabel)},
		{label: 'Model', value: formatModel(model, allowedModels)},
		{
			label: 'Usage',
			value: totalActualTokens > 0
				? `${formatTokenCount(inputTokens)} in / ${formatTokenCount(outputTokens)} out`
				: 'no metered turn yet',
			tone: totalActualTokens > 0 ? 'ok' : 'neutral',
		},
		{
			label: 'Transcript',
			value: estimatedTokens > 0 ? `${formatTokenCount(estimatedTokens)} estimated` : 'empty',
		},
		{label: 'Approvals', value: permissionMode},
	];

	const actionPriority = authReady
		? ['/usage', '/rate-limit-options', '/model', '/privacy-settings']
		: ['/provider', '/login', '/privacy-settings', '/model'];
	const actions = actionPriority
		.map((command) => COMMAND_DETAILS.find((item) => item.command === command))
		.filter((item): item is ReadinessAction => Boolean(item) && commandAvailable(item.command))
		.slice(0, 4);

	return {
		statusLine,
		rows,
		actions,
		footnote: 'Local readiness only; provider quotas, billing, and rate limits remain external.',
	};
}

export function CommercialReadinessPanel({
	status = {},
	commands = [],
}: {
	status?: Record<string, unknown>;
	commands?: string[];
}): React.JSX.Element {
	const {theme} = useTheme();
	const summary = buildCommercialReadiness(status, commands);

	return (
		<Box flexDirection="column" borderStyle="round" borderColor={theme.colors.secondary} paddingX={1} marginTop={1}>
			<Text color={theme.colors.primary} bold>
				Commercial readiness
			</Text>
			<Text dimColor>{summary.statusLine}</Text>
			{summary.rows.map((row) => (
				<Text key={row.label}>
					<Text dimColor>{row.label}: </Text>
					<Text color={toneColor(row.tone, theme.colors.success, theme.colors.warning)}>{row.value}</Text>
				</Text>
			))}
			{summary.actions.length > 0 ? (
				<>
					<Text color={theme.colors.secondary} bold>
						Next actions
					</Text>
					{summary.actions.map((action) => (
						<Text key={action.command}>
							<Text color={theme.colors.primary}>{action.command}</Text>
							<Text dimColor> - {action.label}</Text>
						</Text>
					))}
				</>
			) : null}
			<Text dimColor>{summary.footnote}</Text>
		</Box>
	);
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

function readableNumber(value: unknown): number {
	if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) {
		return 0;
	}
	return Math.round(value);
}

function readableStringList(value: unknown): string[] {
	if (!Array.isArray(value)) {
		return [];
	}
	return value.filter((item): item is string => typeof item === 'string' && item.trim().length > 0);
}

function isConfiguredAuth(value: string): boolean {
	const normalized = value.toLowerCase();
	if (
		normalized.includes('missing')
		|| normalized.includes('invalid')
		|| normalized.includes('expired')
		|| normalized.includes('unconfigured')
		|| normalized.includes('not configured')
	) {
		return false;
	}
	return normalized.includes('configured') || normalized.includes('ready') || normalized.includes('valid');
}

function formatProfile(activeProfile: string, profileLabel: string): string {
	return activeProfile === profileLabel ? activeProfile : `${activeProfile} (${profileLabel})`;
}

function formatModel(model: string, allowedModels: string[]): string {
	if (allowedModels.length === 0) {
		return `${model} (unpinned catalog)`;
	}
	const sample = allowedModels.slice(0, 3).join(', ');
	const suffix = allowedModels.length > 3 ? ` +${allowedModels.length - 3}` : '';
	return `${model} (${sample}${suffix})`;
}

function formatTokenCount(value: number): string {
	if (value >= 1_000_000) {
		return `${(value / 1_000_000).toFixed(1)}m`;
	}
	if (value >= 1000) {
		return `${(value / 1000).toFixed(1)}k`;
	}
	return String(value);
}

function toneColor(tone: ReadinessTone | undefined, success: string, warning: string): string | undefined {
	if (tone === 'ok') {
		return success;
	}
	if (tone === 'warn') {
		return warning;
	}
	return undefined;
}
