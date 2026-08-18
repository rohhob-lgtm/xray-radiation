import { useState } from 'react';
import { Linkedin, Send, Copy, Trash2, Loader2, Sparkles, Hash, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { useAuth } from '@workspace/replit-auth-web';
import { useToast } from '@/hooks/use-toast';
import { useListLinkedInPosts, useGenerateLinkedInPost, useDeleteLinkedInPost, getListLinkedInPostsQueryKey } from '@workspace/api-client-react';
import { useQueryClient } from '@tanstack/react-query';

export default function LinkedInPage() {
  const { user } = useAuth();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const { data: posts, isLoading: isListLoading } = useListLinkedInPosts();

  const [topic, setTopic] = useState('');
  const [tone, setTone] = useState<string>('professional');
  const [length, setLength] = useState<string>('medium');
  const [format, setFormat] = useState<string>('post');
  const [keywordInput, setKeywordInput] = useState('');
  const [keywords, setKeywords] = useState<string[]>([]);
  const [includeHashtags, setIncludeHashtags] = useState(true);

  const FORMAT_PREFIXES: Record<string, string> = {
    post:         '',
    article_intro:'[FORMAT: LinkedIn Article Introduction — compelling hook + 3 key insight paragraphs + CTA, ~500 words, no emojis]',
    carousel:     '[FORMAT: LinkedIn Carousel Post — write a title slide + 7 content slide captions + closing CTA slide, each slide max 30 words]',
    newsletter:   '[FORMAT: LinkedIn Newsletter Blurb — subject line + opening hook + 3 bullet insights + CTA link placeholder, ~180 words]',
  };

  const { mutate: generate, isPending: isGenerating, data: currentPost } = useGenerateLinkedInPost({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: getListLinkedInPostsQueryKey() });
      }
    }
  });

  const { mutate: deletePost } = useDeleteLinkedInPost({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: getListLinkedInPostsQueryKey() });
      }
    }
  });

  const handleAddKeyword = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && keywordInput.trim()) {
      e.preventDefault();
      if (!keywords.includes(keywordInput.trim())) {
        setKeywords([...keywords, keywordInput.trim()]);
      }
      setKeywordInput('');
    }
  };

  const handleGenerate = () => {
    if (!topic.trim()) return;
    const prefix = FORMAT_PREFIXES[format] || '';
    generate({
      data: {
        topic: prefix ? `${prefix}\n\n${topic}` : topic,
        tone: tone as any,
        length: length as any,
        keywords: keywords.length > 0 ? keywords : undefined,
        include_hashtags: includeHashtags
      }
    });
  };

  const handleCopy = (content: string) => {
    navigator.clipboard.writeText(content);
    toast({
      title: "Copied to clipboard",
      description: "Post content is ready to be pasted into LinkedIn.",
    });
  };

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      <div className="p-6 md:p-8 max-w-7xl mx-auto w-full space-y-8">
        
        <div className="flex flex-col gap-2">
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
            <Linkedin className="h-8 w-8 text-[#0A66C2]" />
            Post Generator
          </h1>
          <p className="text-muted-foreground uppercase font-mono tracking-wider text-sm">Professional Authority Broadcast Module</p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          {/* Form */}
          <div className="lg:col-span-5 flex flex-col gap-6 p-6 rounded-xl border border-border bg-card shadow-sm">
            <h2 className="text-lg font-semibold tracking-tight border-b border-border pb-4 flex items-center gap-2">
              <Sparkles className="h-5 w-5 text-primary" />
              Content Parameters
            </h2>

            <div className="grid gap-5">
              <div className="grid gap-2">
                <label className="text-xs font-mono uppercase tracking-widest text-muted-foreground font-semibold">Subject Matter *</label>
                <Textarea 
                  placeholder="e.g., The evolution of dual-energy X-ray in airport security..."
                  value={topic}
                  onChange={(e) => setTopic(e.target.value)}
                  className="resize-none h-24 bg-background border-border"
                />
              </div>

              <div className="grid gap-2">
                <label className="text-xs font-mono uppercase tracking-widest text-muted-foreground font-semibold">Content Format</label>
                <div className="grid grid-cols-2 gap-1.5">
                  {[
                    { id: 'post',         label: 'Post',         sub: '150–300 words' },
                    { id: 'article_intro', label: 'Article Intro', sub: '~500 words' },
                    { id: 'carousel',     label: 'Carousel',     sub: '8 slide captions' },
                    { id: 'newsletter',   label: 'Newsletter',   sub: '~180 words' },
                  ].map(f => (
                    <button key={f.id} onClick={() => setFormat(f.id)}
                      className={`p-2.5 rounded-lg border text-left transition-all ${format === f.id ? 'border-primary bg-primary/10 text-primary' : 'border-border bg-background text-muted-foreground hover:border-primary/40'}`}>
                      <div className="text-xs font-bold">{f.label}</div>
                      <div className="text-[10px] opacity-70 mt-0.5">{f.sub}</div>
                    </button>
                  ))}
                </div>
              </div>

              <div className="grid gap-2">
                <label className="text-xs font-mono uppercase tracking-widest text-muted-foreground font-semibold">Voice / Tone</label>
                <Select value={tone} onValueChange={setTone}>
                  <SelectTrigger className="bg-background">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="professional">Professional & Authoritative</SelectItem>
                    <SelectItem value="educational">Educational / Explainer</SelectItem>
                    <SelectItem value="thought_leadership">Thought Leadership</SelectItem>
                    <SelectItem value="case_study">Case Study / Analytical</SelectItem>
                    <SelectItem value="tips">Practical Tips / Advice</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="grid gap-2">
                <label className="text-xs font-mono uppercase tracking-widest text-muted-foreground font-semibold">Post Length</label>
                <div className="flex p-1 bg-background rounded-lg border border-border w-full">
                  {['short', 'medium', 'long'].map((l) => (
                    <button
                      key={l}
                      onClick={() => setLength(l)}
                      className={`flex-1 text-xs uppercase font-mono tracking-wider py-2 rounded-md transition-colors ${
                        length === l ? 'bg-primary text-primary-foreground font-bold shadow-sm' : 'text-muted-foreground hover:bg-secondary'
                      }`}
                    >
                      {l}
                    </button>
                  ))}
                </div>
              </div>

              <div className="grid gap-2">
                <label className="text-xs font-mono uppercase tracking-widest text-muted-foreground font-semibold">Keywords (Press Enter)</label>
                <div className="flex flex-col gap-2">
                  <Input 
                    placeholder="Add keyword..."
                    value={keywordInput}
                    onChange={(e) => setKeywordInput(e.target.value)}
                    onKeyDown={handleAddKeyword}
                    className="bg-background"
                  />
                  {keywords.length > 0 && (
                    <div className="flex flex-wrap gap-2 mt-1">
                      {keywords.map(kw => (
                        <Badge key={kw} variant="secondary" className="pl-2 pr-1 py-1 text-xs">
                          {kw}
                          <button onClick={() => setKeywords(keywords.filter(k => k !== kw))} className="ml-1 hover:text-destructive">
                            <X className="h-3 w-3" />
                          </button>
                        </Badge>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              <div className="flex items-center justify-between p-4 rounded-lg bg-background border border-border">
                <div className="space-y-0.5">
                  <label className="text-sm font-medium">Include Hashtags</label>
                  <p className="text-xs text-muted-foreground">Automatically generate relevant tags</p>
                </div>
                <Switch checked={includeHashtags} onCheckedChange={setIncludeHashtags} />
              </div>

              <Button 
                onClick={handleGenerate} 
                disabled={!topic.trim() || isGenerating}
                className="w-full mt-2 h-12 text-base font-semibold shadow-sm"
                data-testid="button-generate"
              >
                {isGenerating ? (
                  <>
                    <Loader2 className="h-5 w-5 mr-2 animate-spin" />
                    Synthesizing...
                  </>
                ) : (
                  <>
                    <Send className="h-5 w-5 mr-2" />
                    Generate Post
                  </>
                )}
              </Button>
            </div>
          </div>

          {/* Preview Panel */}
          <div className="lg:col-span-7 flex flex-col gap-6 p-6 rounded-xl border border-border bg-card shadow-sm h-full relative">
            <div className="flex items-center justify-between border-b border-border pb-4">
              <h2 className="text-lg font-semibold tracking-tight flex items-center gap-2">
                <Linkedin className="h-5 w-5 text-primary" />
                Live Preview
              </h2>
              {currentPost && (
                <Button variant="outline" size="sm" onClick={() => handleCopy(currentPost.content)} className="h-8 gap-2 bg-background">
                  <Copy className="h-4 w-4" />
                  Copy Text
                </Button>
              )}
            </div>

            {!currentPost ? (
              <div className="flex-1 flex flex-col items-center justify-center text-center opacity-50 min-h-[300px]">
                <Send className="h-12 w-12 mb-4 text-muted-foreground opacity-50" />
                <p className="text-sm font-mono uppercase tracking-widest text-muted-foreground">Ready to generate</p>
              </div>
            ) : (
              <div className="flex-1 bg-background border border-border rounded-xl p-6 shadow-sm max-w-xl mx-auto w-full animate-in fade-in zoom-in-95 duration-400">
                <div className="flex items-center gap-3 mb-4">
                  <Avatar className="h-12 w-12 border border-border">
                    <AvatarImage src={user?.profile_image || undefined} />
                    <AvatarFallback className="bg-primary/10 text-primary font-bold">{user?.name?.substring(0, 2).toUpperCase() || 'OP'}</AvatarFallback>
                  </Avatar>
                  <div>
                    <h3 className="font-bold text-sm text-foreground">{user?.name || 'Operator'}</h3>
                    <p className="text-xs text-muted-foreground">X-Ray Academy • 1st</p>
                    <p className="text-[10px] text-muted-foreground font-mono">Just now • 🌎</p>
                  </div>
                </div>
                
                <div className="text-sm text-foreground whitespace-pre-wrap leading-relaxed">
                  {currentPost.content}
                </div>
                
                {currentPost.hashtags && currentPost.hashtags.length > 0 && (
                  <div className="mt-4 flex flex-wrap gap-1">
                    {currentPost.hashtags.map(tag => (
                      <span key={tag} className="text-primary font-medium hover:underline cursor-pointer text-sm">
                        {tag.startsWith('#') ? tag : `#${tag}`}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* History Grid */}
        <div className="pt-8 border-t border-border mt-8">
          <h2 className="text-lg font-semibold tracking-tight mb-6">Broadcast History</h2>
          
          {isListLoading ? (
            <div className="text-center text-muted-foreground animate-pulse font-mono text-xs uppercase tracking-widest py-10">Loading history...</div>
          ) : posts?.length === 0 ? (
            <div className="text-center text-muted-foreground font-mono text-xs uppercase tracking-widest py-10 border border-dashed border-border rounded-xl">No previous broadcasts</div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
              {posts?.map(post => (
                <div key={post.id} className="flex flex-col bg-card border border-border rounded-xl p-5 hover:border-primary/50 transition-colors group">
                  <div className="flex justify-between items-start mb-3">
                    <Badge variant="secondary" className="font-mono text-[10px] uppercase tracking-wider bg-secondary text-secondary-foreground">{post.tone}</Badge>
                    <span className="text-[10px] text-muted-foreground font-mono">{new Date(post.created_at).toLocaleDateString()}</span>
                  </div>
                  <h3 className="font-bold text-sm mb-2 line-clamp-1" title={post.topic}>{post.topic}</h3>
                  <p className="text-xs text-muted-foreground line-clamp-3 mb-4 flex-1">
                    {post.content}
                  </p>
                  <div className="flex items-center justify-end gap-2 pt-3 border-t border-border">
                    <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-primary" onClick={() => handleCopy(post.content)}>
                      <Copy className="h-4 w-4" />
                    </Button>
                    <Button 
                      variant="ghost" 
                      size="icon" 
                      className="h-8 w-8 text-muted-foreground hover:text-destructive hover:bg-destructive/10 opacity-0 group-hover:opacity-100 transition-opacity"
                      onClick={() => deletePost({ postId: post.id })}
                      data-testid={`button-delete-post-${post.id}`}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

      </div>
    </div>
  );
}