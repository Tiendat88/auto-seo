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
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { createCampaign } from "@/lib/api";
import type { BrandVoice } from "@/lib/types";
import { toast } from "sonner";
import { Sparkles, Layers } from "lucide-react";

const LANGUAGES = [
  { value: "en", label: "English" },
  { value: "es", label: "Spanish" },
  { value: "fr", label: "French" },
  { value: "de", label: "German" },
  { value: "pt", label: "Portuguese" },
  { value: "vi", label: "Vietnamese" },
  { value: "ja", label: "Japanese" },
  { value: "ko", label: "Korean" },
  { value: "zh", label: "Chinese" },
];

export default function NewCampaignPage() {
  const router = useRouter();
  const [mainKeyword, setMainKeyword] = useState("");
  const [numKeywords, setNumKeywords] = useState(5);
  const [wordCount, setWordCount] = useState(1500);
  const [language, setLanguage] = useState("vi");
  const [webhookUrl, setWebhookUrl] = useState("");
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
    if (mainKeyword.length < 3) {
      toast.error("Từ khóa phải có ít nhất 3 ký tự");
      return;
    }
    setSubmitting(true);
    try {
      const bv = showBrandVoice ? brandVoice : undefined;
      const campaign = await createCampaign({
        main_keyword: mainKeyword,
        num_keywords: numKeywords,
        target_word_count: wordCount,
        language,
        brand_voice: bv,
        webhook_url: webhookUrl.trim() || undefined,
      });
      toast.success(`Đã tạo chiến dịch với ${campaign.jobs.length} bài viết!`);
      router.push(`/pipeline`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Tạo chiến dịch thất bại");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="flex items-center gap-3">
        <div className="p-3 bg-blue-500/10 rounded-xl">
          <Layers className="w-6 h-6 text-blue-500" />
        </div>
        <div>
          <h1 className="text-2xl font-bold">Tạo Chiến Dịch SEO Mới</h1>
          <p className="text-sm text-muted-foreground mt-1">AI sẽ tự động nghiên cứu từ khóa phụ và viết hàng loạt bài viết.</p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        <Card className="border-blue-500/20 shadow-lg shadow-blue-500/5">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-blue-500" />
              Thông tin Chiến dịch
            </CardTitle>
            <CardDescription>Nhập từ khóa chính, AI sẽ lo phần còn lại.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="space-y-2">
              <label className="text-sm font-medium">Từ khóa chính (Seed Keyword)</label>
              <Input
                value={mainKeyword}
                onChange={(e) => setMainKeyword(e.target.value)}
                placeholder="VD: Máy lọc nước, Cách học tiếng Anh..."
                minLength={3}
                maxLength={200}
                required
                className="text-lg py-6"
              />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="space-y-2">
                <label className="text-sm font-medium">Số lượng bài viết</label>
                <Input
                  type="number"
                  value={numKeywords}
                  onChange={(e) => setNumKeywords(Number(e.target.value))}
                  min={1}
                  max={20}
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Độ dài mỗi bài (Từ)</label>
                <Input
                  type="number"
                  value={wordCount}
                  onChange={(e) => setWordCount(Number(e.target.value))}
                  min={300}
                  max={10000}
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Ngôn ngữ</label>
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

            <div className="space-y-2">
              <label className="text-sm font-medium">Custom Webhook URL (Auto-post)</label>
              <Input
                type="url"
                value={webhookUrl}
                onChange={(e) => setWebhookUrl(e.target.value)}
                placeholder="VD: https://your-website.com/api/webhooks/campaign"
              />
              <p className="text-xs text-muted-foreground">
                Hệ thống sẽ tự động POST dữ liệu các bài viết (JSON) tới URL này khi hoàn thành.
              </p>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Brand Voice (Giọng điệu Thương hiệu)</CardTitle>
                <CardDescription>Định hình phong cách viết để tránh mùi AI.</CardDescription>
              </div>
              <Button
                type="button"
                variant={showBrandVoice ? "destructive" : "secondary"}
                size="sm"
                onClick={() => setShowBrandVoice(!showBrandVoice)}
              >
                {showBrandVoice ? "Tắt" : "Bật"}
              </Button>
            </div>
          </CardHeader>
          {showBrandVoice && (
            <CardContent className="space-y-4 animate-in slide-in-from-top-2">
              <div className="space-y-2">
                <label className="text-sm font-medium">Tên Thương hiệu</label>
                <Input
                  value={brandVoice.brand_name ?? ""}
                  onChange={(e) =>
                    setBrandVoice({ ...brandVoice, brand_name: e.target.value || null })
                  }
                  placeholder="VD: Vinamilk, The Coffee House..."
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Mô tả Giọng điệu</label>
                <Textarea
                  value={brandVoice.voice_description ?? ""}
                  onChange={(e) =>
                    setBrandVoice({ ...brandVoice, voice_description: e.target.value || null })
                  }
                  placeholder="VD: Chuyên nghiệp, đáng tin cậy, nhưng vẫn gần gũi..."
                  rows={3}
                />
              </div>
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <label className="text-sm font-medium">Bài viết mẫu (Tối đa 3)</label>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      if (brandVoice.writing_examples.length < 3) {
                        setBrandVoice({
                          ...brandVoice,
                          writing_examples: [...brandVoice.writing_examples, ""],
                        });
                      }
                    }}
                    disabled={brandVoice.writing_examples.length >= 3}
                  >
                    Thêm mẫu
                  </Button>
                </div>
                {brandVoice.writing_examples.map((example, i) => (
                  <div key={i} className="flex gap-2">
                    <Textarea
                      value={example}
                      onChange={(e) => {
                        const newExamples = [...brandVoice.writing_examples];
                        newExamples[i] = e.target.value;
                        setBrandVoice({ ...brandVoice, writing_examples: newExamples });
                      }}
                      placeholder={`Ví dụ ${i + 1}...`}
                      rows={2}
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      onClick={() => {
                        const newExamples = brandVoice.writing_examples.filter((_, idx) => idx !== i);
                        setBrandVoice({ ...brandVoice, writing_examples: newExamples });
                      }}
                    >
                      <span className="text-destructive font-bold text-lg leading-none">&times;</span>
                    </Button>
                  </div>
                ))}
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Lưu ý Văn phong (Style Notes)</label>
                <Textarea
                  value={brandVoice.style_notes ?? ""}
                  onChange={(e) =>
                    setBrandVoice({ ...brandVoice, style_notes: e.target.value || null })
                  }
                  placeholder="Bất kỳ quy tắc cứng nào (VD: luôn xưng hô chúng tôi, không dùng từ chê bai)..."
                  rows={2}
                />
              </div>
            </CardContent>
          )}
        </Card>

        <Button 
          type="submit" 
          className="w-full h-12 text-lg bg-blue-600 hover:bg-blue-700 text-white"
          disabled={submitting || mainKeyword.length < 3}
        >
          {submitting ? (
            <span className="flex items-center gap-2">
              <span className="animate-spin">⏳</span> Đang suy nghĩ từ khóa \u0026 tạo chiến dịch...
            </span>
          ) : (
            "Khởi chạy Chiến dịch Tự động"
          )}
        </Button>
      </form>
    </div>
  );
}
