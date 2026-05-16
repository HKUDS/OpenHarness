import { useAppStore } from '../store/useAppStore';
import type { ChannelConfig, DiscordConfig, TelegramConfig } from '../types';
import { MessageSquare, Send, Plus, Trash2, Power } from 'lucide-react';
import { useState } from 'react';
import styles from './PageLayout.module.css';

type ChannelType = 'discord' | 'telegram';

export function ChannelsPage() {
  const { channels, addChannel, removeChannel, toggleChannel } = useAppStore();
  const [showAddForm, setShowAddForm] = useState(false);
  const [newChannelType, setNewChannelType] = useState<ChannelType>('discord');
  const [newChannel, setNewChannel] = useState({
    name: '',
    botToken: '',
    channelId: '',
    guildId: '',
    threadId: '',
    prefix: '!'
  });
  
  const discordChannels = channels.filter(c => c.type === 'discord');
  const telegramChannels = channels.filter(c => c.type === 'telegram');
  const enabledChannels = channels.filter(c => c.enabled);
  
  const handleAddChannel = () => {
    if (!newChannel.name || !newChannel.botToken || !newChannel.channelId) return;
    
    const channel: ChannelConfig = {
      id: `channel-${Date.now()}`,
      type: newChannelType,
      enabled: true,
      name: newChannel.name,
      config: newChannelType === 'discord' 
        ? {
            botToken: newChannel.botToken,
            channelId: newChannel.channelId,
            guildId: newChannel.guildId,
            prefix: newChannel.prefix
          } as DiscordConfig
        : {
            botToken: newChannel.botToken,
            chatId: newChannel.channelId,
            threadId: newChannel.threadId
          } as TelegramConfig
    };
    
    addChannel(channel);
    setNewChannel({
      name: '',
      botToken: '',
      channelId: '',
      guildId: '',
      threadId: '',
      prefix: '!'
    });
    setShowAddForm(false);
  };
  
  const resetForm = () => {
    setNewChannel({
      name: '',
      botToken: '',
      channelId: '',
      guildId: '',
      threadId: '',
      prefix: '!'
    });
    setShowAddForm(false);
  };
  
  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <h1><MessageSquare size={24} /> Channels</h1>
        <p>Configure Discord and Telegram message channels</p>
      </div>
      
      <div className={styles.statsGrid}>
        <div className={styles.statCard}>
          <span className={styles.statValue}>{discordChannels.length}</span>
          <span className={styles.statLabel}>Discord</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statValue}>{telegramChannels.length}</span>
          <span className={styles.statLabel}>Telegram</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statValue}>{enabledChannels.length}</span>
          <span className={styles.statLabel}>Enabled</span>
        </div>
      </div>
      
      <div className={styles.pageContent}>
        <div className={styles.pageToolbar}>
          <button 
            className={styles.primaryButton}
            onClick={() => setShowAddForm(!showAddForm)}
          >
            <Plus size={18} />
            Add Channel
          </button>
        </div>
        
        {showAddForm && (
          <div className={styles.formCard}>
            <h3>Add New Channel</h3>
            
            <div className={styles.formGroup}>
              <label>Channel Type</label>
              <div className={styles.typeSelector}>
                <button
                  type="button"
                  className={`${styles.typeButton} ${newChannelType === 'discord' ? styles.active : ''}`}
                  onClick={() => setNewChannelType('discord')}
                >
                  <MessageSquare size={16} />
                  Discord
                </button>
                <button
                  type="button"
                  className={`${styles.typeButton} ${newChannelType === 'telegram' ? styles.active : ''}`}
                  onClick={() => setNewChannelType('telegram')}
                >
                  <Send size={16} />
                  Telegram
                </button>
              </div>
            </div>
            
            <div className={styles.formGroup}>
              <label>Channel Name</label>
              <input
                type="text"
                value={newChannel.name}
                onChange={(e) => setNewChannel({ ...newChannel, name: e.target.value })}
                placeholder="My Discord Bot"
              />
            </div>
            
            <div className={styles.formGroup}>
              <label>Bot Token</label>
              <input
                type="password"
                value={newChannel.botToken}
                onChange={(e) => setNewChannel({ ...newChannel, botToken: e.target.value })}
                placeholder={newChannelType === 'discord' ? 'OTk5OTk5OTk5OTk5OTk5OTk5.XXXXXX.XXXXXXXXXXXXXXXXXXXXXXXXXXXX' : '123456789:ABCdefGHIjklMNOpqrSTUvwxYZ1234567890'}
              />
            </div>
            
            <div className={styles.formGroup}>
              <label>{newChannelType === 'discord' ? 'Channel ID' : 'Chat ID'}</label>
              <input
                type="text"
                value={newChannel.channelId}
                onChange={(e) => setNewChannel({ ...newChannel, channelId: e.target.value })}
                placeholder={newChannelType === 'discord' ? '123456789012345678' : '-1001234567890'}
              />
            </div>
            
            {newChannelType === 'discord' && (
              <>
                <div className={styles.formGroup}>
                  <label>Guild ID (Optional)</label>
                  <input
                    type="text"
                    value={newChannel.guildId}
                    onChange={(e) => setNewChannel({ ...newChannel, guildId: e.target.value })}
                    placeholder="123456789012345678"
                  />
                </div>
                <div className={styles.formGroup}>
                  <label>Command Prefix</label>
                  <input
                    type="text"
                    value={newChannel.prefix}
                    onChange={(e) => setNewChannel({ ...newChannel, prefix: e.target.value })}
                    placeholder="!"
                  />
                </div>
              </>
            )}
            
            {newChannelType === 'telegram' && (
              <div className={styles.formGroup}>
                <label>Thread ID (Optional)</label>
                <input
                  type="text"
                  value={newChannel.threadId}
                  onChange={(e) => setNewChannel({ ...newChannel, threadId: e.target.value })}
                  placeholder="12345"
                />
              </div>
            )}
            
            <div className={styles.formActions}>
              <button className={styles.secondaryButton} onClick={resetForm}>
                Cancel
              </button>
              <button 
                className={styles.primaryButton} 
                onClick={handleAddChannel}
                disabled={!newChannel.name || !newChannel.botToken || !newChannel.channelId}
              >
                Add Channel
              </button>
            </div>
          </div>
        )}
        
        {channels.length === 0 ? (
          <div className={styles.emptyState}>
            <MessageSquare size={48} />
            <h3>No channels configured</h3>
            <p>Add a Discord or Telegram channel to enable message notifications</p>
          </div>
        ) : (
          <div className={styles.channelList}>
            {channels.map((channel) => (
              <div key={channel.id} className={`${styles.channelCard} ${channel.enabled ? styles.enabled : ''}`}>
                <div className={styles.channelHeader}>
                  <div className={styles.channelIcon}>
                    {channel.type === 'discord' ? <MessageSquare size={20} /> : <Send size={20} />}
                  </div>
                  <div className={styles.channelInfo}>
                    <span className={styles.channelName}>{channel.name}</span>
                    <span className={styles.channelType}>{channel.type}</span>
                  </div>
                  <span className={`${styles.status} ${channel.enabled ? styles.enabled : styles.disabled}`}>
                    <Power size={12} />
                    {channel.enabled ? 'Enabled' : 'Disabled'}
                  </span>
                </div>
                
                <div className={styles.channelDetails}>
                  {channel.type === 'discord' && (
                    <>
                      <div className={styles.detailItem}>
                        <span className={styles.detailLabel}>Channel ID</span>
                        <span className={styles.detailValue}>{(channel.config as DiscordConfig).channelId}</span>
                      </div>
                      {(channel.config as DiscordConfig).prefix && (
                        <div className={styles.detailItem}>
                          <span className={styles.detailLabel}>Prefix</span>
                          <span className={styles.detailValue}>{(channel.config as DiscordConfig).prefix}</span>
                        </div>
                      )}
                    </>
                  )}
                  {channel.type === 'telegram' && (
                    <div className={styles.detailItem}>
                      <span className={styles.detailLabel}>Chat ID</span>
                      <span className={styles.detailValue}>{(channel.config as TelegramConfig).chatId}</span>
                    </div>
                  )}
                </div>
                
                <div className={styles.channelActions}>
                  <button 
                    className={`${styles.iconButton} ${channel.enabled ? styles.success : ''}`}
                    onClick={() => toggleChannel(channel.id)}
                    title={channel.enabled ? 'Disable' : 'Enable'}
                  >
                    {channel.enabled ? <Power size={16} /> : <Power size={16} />}
                  </button>
                  <button 
                    className={`${styles.iconButton} ${styles.danger}`}
                    onClick={() => removeChannel(channel.id)}
                    title="Remove"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}