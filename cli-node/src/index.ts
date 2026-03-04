#!/usr/bin/env node

import { Command } from 'commander';
import axios from 'axios';

const program = new Command();
const SERVER_URL = process.env.TALK_MEMORY_SERVER || 'http://localhost:7900';

program
  .name('talk-memory')
  .description('Manage conversation data from various chat platforms')
  .version('0.1.0');

// serve command
program
  .command('serve')
  .description('Start the talk-memory server')
  .option('--host <host>', 'Host to bind to', 'localhost')
  .option('--port <port>', 'Port to bind to', '7900')
  .option('--reload', 'Enable auto-reload')
  .action((options) => {
    console.log(`Starting server at http://${options.host}:${options.port}`);
    // Note: This would typically spawn the server process
    console.log('Use server-py or server-node to start the server directly');
  });

// pull command
program
  .command('pull [platform]')
  .description('Trigger exporters to pull conversation data')
  .option('--all', 'Run all configured exporters')
  .option('--server <url>', 'Server URL', SERVER_URL)
  .action((platform, options) => {
    if (!platform && !options.all) {
      console.error('Error: Please specify a platform or use --all');
      process.exit(1);
    }
    console.log(`Pull command called for platform: ${platform || 'all'}`);
    console.log('Exporters should POST to <server>/api/ingest');
  });

// list command
program
  .command('list [platform]')
  .description('List all conversations')
  .option('--server <url>', 'Server URL', SERVER_URL)
  .action(async (platform, options) => {
    try {
      let url = `${options.server}/api/conversations`;
      if (platform) {
        url += `?platform=${platform}`;
      }

      const response = await axios.get(url);
      const conversations = response.data;

      if (conversations.length === 0) {
        console.log('No conversations found.');
        return;
      }

      console.log(`${'Platform'.padEnd(15)} ${'Session ID'.padEnd(20)} ${'Title'.padEnd(30)} ${'Messages'.padEnd(10)} ${'Updated'.padEnd(20)}`);
      console.log('-'.repeat(95));

      for (const conv of conversations) {
        const title = (conv.title || '').substring(0, 28);
        const sessionId = (conv.session_id || '').substring(0, 18);
        const platformName = (conv.platform || '').substring(0, 13);
        const msgCount = String(conv.message_count || 0).padEnd(8);
        const updated = (conv.updated_at || '').substring(0, 19);

        console.log(`${platformName.padEnd(15)} ${sessionId.padEnd(20)} ${title.padEnd(30)} ${msgCount.padEnd(10)} ${updated.padEnd(20)}`);
      }
    } catch (error: any) {
      if (error.code === 'ECONNREFUSED') {
        console.error(`Error: Cannot connect to server at ${options.server}`);
        console.error('Make sure the server is running with "talk-memory serve"');
      } else {
        console.error(`Error: ${error.message}`);
      }
      process.exit(1);
    }
  });

// search command
program
  .command('search <query>')
  .description('Search conversations by keyword')
  .option('--platform <platform>', 'Filter by platform')
  .option('--server <url>', 'Server URL', SERVER_URL)
  .action(async (query, options) => {
    try {
      const url = `${options.server}/api/search?q=${encodeURIComponent(query)}`;
      const response = await axios.get(url);
      let results = response.data;

      if (options.platform) {
        results = results.filter((r: any) => r.platform === options.platform);
      }

      if (results.length === 0) {
        console.log(`No results found for '${query}'`);
        return;
      }

      console.log(`Found ${results.length} result(s):\n`);

      results.forEach((result: any, i: number) => {
        console.log(`${i + 1}. [${result.platform}] ${result.title}`);
        console.log(`   ${result.matched_message?.substring(0, 100)}...`);
        console.log('');
      });
    } catch (error: any) {
      if (error.code === 'ECONNREFUSED') {
        console.error(`Error: Cannot connect to server at ${options.server}`);
        console.error('Make sure the server is running with "talk-memory serve"');
      } else {
        console.error(`Error: ${error.message}`);
      }
      process.exit(1);
    }
  });

// export command
program
  .command('export <session-id>')
  .description('Export a conversation')
  .option('--platform <platform>', 'Platform name', 'chatgpt')
  .option('--format <format>', 'Output format', 'json')
  .option('--output <file>', 'Output file')
  .option('--server <url>', 'Server URL', SERVER_URL)
  .action(async (sessionId, options) => {
    try {
      const url = `${options.server}/api/conversations/${options.platform}/${sessionId}`;
      const response = await axios.get(url);
      const data = response.data;

      let content: string;
      if (options.format === 'json') {
        content = JSON.stringify(data, null, 2);
      } else if (options.format === 'md') {
        content = formatAsMarkdown(data.metadata, data.messages);
      } else {
        content = formatAsText(data.metadata, data.messages);
      }

      if (options.output) {
        const fs = require('fs');
        fs.writeFileSync(options.output, content);
        console.log(`Exported to ${options.output}`);
      } else {
        console.log(content);
      }
    } catch (error: any) {
      if (error.response?.status === 404) {
        console.error(`Error: Conversation '${sessionId}' not found on platform '${options.platform}'`);
      } else if (error.code === 'ECONNREFUSED') {
        console.error(`Error: Cannot connect to server at ${options.server}`);
        console.error('Make sure the server is running with "talk-memory serve"');
      } else {
        console.error(`Error: ${error.message}`);
      }
      process.exit(1);
    }
  });

function formatAsMarkdown(metadata: any, messages: any[]): string {
  const lines: string[] = [];
  lines.push(`# ${metadata.title || 'Untitled'}\n`);
  lines.push(`**Platform:** ${metadata.platform || 'unknown'}`);
  lines.push(`**Session ID:** ${metadata.session_id || 'unknown'}`);
  lines.push(`**Created:** ${metadata.created_at || 'unknown'}`);
  lines.push(`**Messages:** ${messages.length}\n`);
  lines.push('---\n');

  for (const msg of messages) {
    const role = (msg.role || 'unknown').capitalize();
    const content = msg.content || '';
    const timestamp = msg.timestamp || '';

    lines.push(`### ${role} (${timestamp})\n`);
    lines.push(content);
    lines.push('\n');
  }

  return lines.join('\n');
}

function formatAsText(metadata: any, messages: any[]): string {
  const lines: string[] = [];
  lines.push(metadata.title || 'Untitled');
  lines.push('='.repeat(50));
  lines.push('');

  for (const msg of messages) {
    const role = (msg.role || 'unknown').toUpperCase();
    const content = msg.content || '';
    lines.push(`[${role}] ${content}`);
    lines.push('');
  }

  return lines.join('\n');
}

// Add capitalize to String prototype
String.prototype.capitalize = function() {
  return this.charAt(0).toUpperCase() + this.slice(1);
};

program.parse();
