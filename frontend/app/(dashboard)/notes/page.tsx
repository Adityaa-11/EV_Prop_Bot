"use client"

import * as React from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"
import { Save, Plus, Trash2, FileText } from "lucide-react"

export default function NotesPage() {
  const [notes, setNotes] = React.useState<string>("")
  const [savedNotes, setSavedNotes] = React.useState<string[]>([])

  // Load saved notes from localStorage on mount
  React.useEffect(() => {
    const saved = localStorage.getItem("ev-dashboard-notes")
    if (saved) {
      setSavedNotes(JSON.parse(saved))
    }
  }, [])

  const saveNote = () => {
    if (!notes.trim()) return
    const updated = [...savedNotes, notes]
    setSavedNotes(updated)
    localStorage.setItem("ev-dashboard-notes", JSON.stringify(updated))
    setNotes("")
  }

  const deleteNote = (index: number) => {
    const updated = savedNotes.filter((_, i) => i !== index)
    setSavedNotes(updated)
    localStorage.setItem("ev-dashboard-notes", JSON.stringify(updated))
  }

  return (
    <div className="container mx-auto px-4 py-6 sm:px-6">
      {/* Page Header */}
      <div className="mb-6">
        <h1 className="text-3xl font-bold">Notes</h1>
        <p className="mt-1 text-sm text-muted-foreground">Personal notes and reference information</p>
      </div>

      <div className="space-y-6">
        {/* PrizePicks Break-Even Table */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <span className="text-2xl">💎</span>
              PrizePicks Break-Even Odds
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Slip</TableHead>
                  <TableHead className="text-right">Break-Even (Implied %)</TableHead>
                  <TableHead className="text-right">Break-Even (American)</TableHead>
                  <TableHead className="text-center">Recommendation</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                <TableRow className="bg-green-500/10">
                  <TableCell className="font-medium">6 Flex</TableCell>
                  <TableCell className="text-right font-mono">54.34%</TableCell>
                  <TableCell className="text-right font-mono">-119</TableCell>
                  <TableCell className="text-center">
                    <Badge className="bg-green-600">✅ BEST VALUE</Badge>
                  </TableCell>
                </TableRow>
                <TableRow className="bg-green-500/10">
                  <TableCell className="font-medium">5 Flex</TableCell>
                  <TableCell className="text-right font-mono">54.34%</TableCell>
                  <TableCell className="text-right font-mono">-119</TableCell>
                  <TableCell className="text-center">
                    <Badge className="bg-green-600">✅ BEST VALUE</Badge>
                  </TableCell>
                </TableRow>
                <TableRow className="bg-yellow-500/10">
                  <TableCell className="font-medium">4 Power</TableCell>
                  <TableCell className="text-right font-mono">56.23%</TableCell>
                  <TableCell className="text-right font-mono">-128</TableCell>
                  <TableCell className="text-center">
                    <Badge variant="outline" className="border-yellow-500 text-yellow-600">⚠️ Good</Badge>
                  </TableCell>
                </TableRow>
                <TableRow className="bg-yellow-500/10">
                  <TableCell className="font-medium">4 Flex</TableCell>
                  <TableCell className="text-right font-mono">56.89%</TableCell>
                  <TableCell className="text-right font-mono">-132</TableCell>
                  <TableCell className="text-center">
                    <Badge variant="outline" className="border-yellow-500 text-yellow-600">⚠️ Good</Badge>
                  </TableCell>
                </TableRow>
                <TableRow className="bg-orange-500/10">
                  <TableCell className="font-medium">2 Power</TableCell>
                  <TableCell className="text-right font-mono">57.74%</TableCell>
                  <TableCell className="text-right font-mono">-137</TableCell>
                  <TableCell className="text-center">
                    <Badge variant="outline" className="border-orange-500 text-orange-600">Need Strong Props</Badge>
                  </TableCell>
                </TableRow>
                <TableRow className="bg-red-500/10">
                  <TableCell className="font-medium">3 Power</TableCell>
                  <TableCell className="text-right font-mono">58.48%</TableCell>
                  <TableCell className="text-right font-mono">-141</TableCell>
                  <TableCell className="text-center">
                    <Badge variant="destructive">❌ AVOID</Badge>
                  </TableCell>
                </TableRow>
                <TableRow className="bg-red-500/10">
                  <TableCell className="font-medium">3 Flex</TableCell>
                  <TableCell className="text-right font-mono">59.80%</TableCell>
                  <TableCell className="text-right font-mono">-149</TableCell>
                  <TableCell className="text-center">
                    <Badge variant="destructive">❌ AVOID</Badge>
                  </TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        {/* Add New Note */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Plus className="h-5 w-5" />
              Add Note
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <Textarea
              placeholder="Add your notes here... (strategies, observations, reminders, etc.)"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className="min-h-[120px]"
            />
            <Button onClick={saveNote} disabled={!notes.trim()}>
              <Save className="mr-2 h-4 w-4" />
              Save Note
            </Button>
          </CardContent>
        </Card>

        {/* Saved Notes */}
        {savedNotes.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <FileText className="h-5 w-5" />
                My Notes ({savedNotes.length})
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {savedNotes.map((note, index) => (
                <div key={index} className="flex gap-3 rounded-lg border p-4">
                  <div className="flex-1 whitespace-pre-wrap text-sm">{note}</div>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 text-muted-foreground hover:text-destructive"
                    onClick={() => deleteNote(index)}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              ))}
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}

