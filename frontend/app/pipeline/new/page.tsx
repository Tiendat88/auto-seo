"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { createJob } from "@/lib/api";
import type { BrandVoice } from "@/lib/types";
import { toast } from "sonner";

const LANGUAGES = [
  { value: "en", label: "English" },
  { value: "es", label: "Spanish" },
  { value: "fr", label: "French" },
  { value: "de", label: "German" },
  { value: "pt", label: "Portuguese" },
  { value: "it", label: "Italian" },
  { value: "nl", label: "Dutch" },
  { value: "ja", label: "Japanese" },
  { value: "ko", label: "Korean" },
  { value: "zh", label: "Chinese" },
];

export default function NewJobPage() {
  const router = useRouter();
  const [topic, setTopic] = useState("");
  const [wordCount, setWordCount] = useState(1500);
  const [language, setLanguage] = useState("en");
  const [showBrandVoice, setShowBrandVoice] = useState(false);
  const [brandVoice, setBrandVoice] = useState<BrandVoice>({
    brand_name: null,
    voice_description: null,
    writing_examples: [],
    style_notes: null,
  });
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (topic.length < 3) {
      toast.error("Topic must be at least 3 characters");
      return;
    }
    setSubmitting(true);
    try {
      const bv = showBrandVoice ? brandVoice : undefined;
      const job = await createJob({
        topic,
        target_word_count: wordCount,
        language,
        brand_voice: bv,
      });
      toast.success("Job created");
      router.push(`/pipeline/${job.job_id}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to create job");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <h1 className="text-2xl font-bold">Create New Job</h1>

      <form onSubmit={handleSubmit} className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>Article Settings</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">Topic</label>
              <Input
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                placeholder="e.g., Best CRM tools for startups in 2026"
                minLength={3}
                maxLength={200}
                required
              />
              <p className="text-xs text-muted-foreground">{topic.length}/200</p>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <label className="text-sm font-medium">Target Word Count</label>
                <Input
                  type="number"
                  value={wordCount}
                  onChange={(e) => setWordCount(Number(e.target.value))}
                  min={300}
                  max={10000}
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Language</label>
                <Select value={language} onValueChange={(v) => { if (v) setLanguage(v); }}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {LANGUAGES.map((lang) => (
                      <SelectItem key={lang.value} value={lang.value}>
                        {lang.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>Brand Voice</CardTitle>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setShowBrandVoice(!showBrandVoice)}
              >
                {showBrandVoice ? "Remove" : "Add"}
              </Button>
            </div>
          </CardHeader>
          {showBrandVoice && (
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <label className="text-sm font-medium">Brand Name</label>
                <Input
                  value={brandVoice.brand_name ?? ""}
                  onChange={(e) =>
                    setBrandVoice({ ...brandVoice, brand_name: e.target.value || null })
                  }
                  placeholder="Your brand name"
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Voice Description</label>
                <Textarea
                  value={brandVoice.voice_description ?? ""}
                  onChange={(e) =>
                    setBrandVoice({ ...brandVoice, voice_description: e.target.value || null })
                  }
                  placeholder="Describe your brand's tone and writing style..."
                  rows={3}
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Style Notes</label>
                <Textarea
                  value={brandVoice.style_notes ?? ""}
                  onChange={(e) =>
                    setBrandVoice({ ...brandVoice, style_notes: e.target.value || null })
                  }
                  placeholder="Any specific style guidelines..."
                  rows={2}
                />
              </div>
            </CardContent>
          )}
        </Card>

        <Button type="submit" className="w-full" disabled={submitting || topic.length < 3}>
          {submitting ? "Creating..." : "Generate Article"}
        </Button>
      </form>
    </div>
  );
}
