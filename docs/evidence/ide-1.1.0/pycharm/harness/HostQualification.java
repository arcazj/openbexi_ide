// SPDX-License-Identifier: GPL-3.0-or-later
// Separate test plugin: this class is never shipped in the runtime ZIP.
package org.openbexi.spell.qualification;

import com.google.gson.GsonBuilder;
import com.intellij.openapi.application.ApplicationManager;
import com.intellij.openapi.application.WriteAction;
import com.intellij.openapi.fileEditor.FileEditorManager;
import com.intellij.openapi.project.Project;
import com.intellij.openapi.startup.StartupActivity;
import com.intellij.openapi.vfs.LocalFileSystem;
import com.intellij.openapi.vfs.VirtualFile;
import com.intellij.openapi.wm.WindowManager;
import com.intellij.openapi.wm.ToolWindowManager;
import com.intellij.xdebugger.*;
import com.intellij.xdebugger.breakpoints.*;
import com.intellij.xdebugger.frame.*;
import com.intellij.xdebugger.evaluation.EvaluationMode;
import com.intellij.execution.process.*;
import com.intellij.openapi.util.Key;
import com.intellij.openapi.actionSystem.*;
import com.intellij.openapi.actionSystem.impl.SimpleDataContext;
import javax.swing.*;
import java.awt.Component;
import java.awt.Container;
import org.openbexi.spell.*;
import java.awt.image.BufferedImage;
import javax.imageio.ImageIO;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.BooleanSupplier;

public final class HostQualification implements StartupActivity.DumbAware {
    private static final AtomicBoolean started = new AtomicBoolean();
    @Override public void runActivity(Project project) {
        if (System.getProperty("openbexi.qualification") == null || !started.compareAndSet(false, true)) return;
        Thread.ofVirtual().name("openbexi-host-qualification").start(() -> qualify(project));
    }
    private static <T> T ui(Callable<T> work) throws Exception {
        FutureTask<T> result = new FutureTask<>(work);
        ApplicationManager.getApplication().invokeLater(result);
        return result.get(30, TimeUnit.SECONDS);
    }
    private static void waitFor(BooleanSupplier condition, String message) throws Exception {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(45);
        while (!condition.getAsBoolean() && System.nanoTime() < deadline) Thread.sleep(25);
        require(condition.getAsBoolean(), message);
    }
    private static void require(boolean value, String message) { if (!value) throw new AssertionError(message); }
    private static VirtualFile source(Project project, String name, String text) throws Exception {
        VirtualFile file = ui(() -> WriteAction.compute(() -> {
            VirtualFile root = LocalFileSystem.getInstance().findFileByPath(project.getBasePath());
            require(root != null, "Project root not visible to IDE");
            VirtualFile created = root.createChildData(HostQualification.class, name);
            created.setBinaryContent(text.getBytes(java.nio.charset.StandardCharsets.UTF_8));
            return created;
        }));
        ui(() -> { FileEditorManager.getInstance(project).openFile(file, true); return null; });
        return file;
    }
    private static ProcessAdapter collect(StringBuffer output) {
        return new ProcessAdapter() {
            @Override public void onTextAvailable(ProcessEvent event, Key type) { output.append(event.getText()); }
        };
    }
    private static <T extends Component> List<T> components(Component root, Class<T> type) {
        List<T> values = new ArrayList<>();
        if (type.isInstance(root)) values.add(type.cast(root));
        if (root instanceof Container parent) for (Component child : parent.getComponents()) values.addAll(components(child, type));
        return values;
    }
    private static JComponent workspace(Project project) {
        return ToolWindowManager.getInstance(project).getToolWindow("SPELL").getContentManager().getContent(0).getComponent();
    }
    private static void button(Project project, String label) {
        components(workspace(project), JButton.class).stream().filter(value -> label.equals(value.getText())).findFirst().orElseThrow().doClick();
    }
    private static void itemInformation(Project project, int line) throws Exception {
        AtomicBoolean verified = new AtomicBoolean();
        ui(() -> {
            long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(15);
            int[] phase = {0};
            javax.swing.Timer timer = new javax.swing.Timer(100, null);
            timer.addActionListener(event -> {
                for (var window : java.awt.Window.getWindows()) if (window instanceof JDialog dialog && dialog.getTitle().startsWith("Item information")) {
                    var tables = components(dialog, JTable.class);
                    var modes = components(dialog, JComboBox.class);
                    boolean loaded = tables.stream().anyMatch(table -> table.getColumnCount() == 7 && table.getRowCount() > 0
                        && "SUCCESS".equals(String.valueOf(table.getValueAt(0, 3))));
                    if (phase[0] < 2 && loaded) { modes.getFirst().setSelectedIndex(++phase[0]); }
                    else if (phase[0] == 2 && components(dialog, JTextArea.class).stream().anyMatch(text -> text.getText().contains("ItemName"))) {
                        verified.set(true); timer.stop(); dialog.dispose();
                    } else if (System.nanoTime() > deadline) { timer.stop(); dialog.dispose(); }
                }
            });
            timer.start();
            try {
                var view = workspace(project);
                var method = view.getClass().getDeclaredMethod("showInformation", SpellWorkspace.Session.class, int.class);
                method.setAccessible(true); method.invoke(view, SpellWorkspace.get(project).selected(), line);
            } finally { timer.stop(); }
            return null;
        });
        require(verified.get(), "Native item-information Latest/History/Full did not load persisted notifications");
    }
    private static void layout(Component value) {
        if (value instanceof Container parent) { parent.doLayout(); for (Component child : parent.getComponents()) layout(child); }
    }
    private static void captureWorkspace(Project project, Path target) throws Exception {
        ui(() -> {
            JComponent content = workspace(project);
            // JTable.removeNotify detaches its header when the private frame is hidden.
            // Restore the normal showing lifecycle before printing the hidden workspace.
            for (JTable table : components(content, JTable.class)) {
                var scroll = (JScrollPane)SwingUtilities.getAncestorOfClass(JScrollPane.class, table);
                if (scroll != null) scroll.setColumnHeaderView(table.getTableHeader());
            }
            content.setSize(1320, 800); layout(content);
            for (JTable table : components(content, JTable.class)) {
                var scroll = (JScrollPane)SwingUtilities.getAncestorOfClass(JScrollPane.class, table);
                if (scroll != null && scroll.isVisible())
                    require(table.getTableHeader() != null && table.getTableHeader().getParent() != null && table.getTableHeader().getHeight() > 0, "Table header is detached or has zero height in workspace");
            }
            var list = components(content, JCheckBox.class).stream().filter(item -> "Procedure list".equals(item.getText())).findFirst().orElseThrow();
            require(!list.isSelected(), "Procedure history must be collapsed while the instance strip remains available");
            StringBuilder diagnostics = new StringBuilder();
            for (JTable table : components(content, JTable.class)) {
                var header = table.getTableHeader();
                diagnostics.append("header=").append(header.getBounds()).append(" visible=").append(header.isVisible()).append(" parent=").append(header.getParent() == null ? "null" : header.getParent().getBounds()).append(" parentVisible=").append(header.getParent() != null && header.getParent().isVisible()).append(" value=").append(table.getColumnModel().getColumn(0).getHeaderValue()).append("\n");
            }
            Files.writeString(Path.of(target.toString() + ".layout.txt"), diagnostics);
            var image = new BufferedImage(1320, 800, BufferedImage.TYPE_INT_RGB);
            var graphics = image.createGraphics(); content.printAll(graphics); graphics.dispose();
            ImageIO.write(image, "png", target.toFile()); return null;
        });
    }
    private static void awaitPrompt(Project project, String label) throws Exception {
        waitFor(() -> {
            try { return ui(() -> { var current = SpellWorkspace.get(project).selected();
                return current != null && current.prompt != null && current.prompt.get("Text").getAsString().equals(label); }); }
            catch (Exception error) { throw new RuntimeException(error); }
        }, "Prompt panel missing: " + label);
    }
    private static XValue variable(XDebugSession session, String name) throws Exception {
        CompletableFuture<XValue> result = new CompletableFuture<>();
        ui(() -> {
            session.getCurrentStackFrame().computeChildren(new XCompositeNode() {
                @Override public boolean isObsolete() { return false; }
                @Override public void addChildren(XValueChildrenList children, boolean last) {
                    for (int i = 0; i < children.size(); i++)
                        if (children.getName(i).equals(name)) result.complete(children.getValue(i));
                    if (last && !result.isDone()) result.completeExceptionally(new AssertionError("Variable missing: " + name));
                }
                @Override public void tooManyChildren(int count) { result.completeExceptionally(new AssertionError("Truncated variables")); }
                @Override public void setAlreadySorted(boolean sorted) { }
                @Override public void setErrorMessage(String text) { result.completeExceptionally(new AssertionError(text)); }
                @Override public void setErrorMessage(String text, XDebuggerTreeNodeHyperlink link) { setErrorMessage(text); }
                @Override public void setMessage(String text, javax.swing.Icon icon, com.intellij.ui.SimpleTextAttributes attrs, XDebuggerTreeNodeHyperlink link) { }
            });
            return null;
        });
        return result.get(15, TimeUnit.SECONDS);
    }
    private void qualify(Project project) {
        Path evidence = Path.of(System.getProperty("openbexi.qualification"));
        Map<String, Object> report = new LinkedHashMap<>();
        List<String> checks = new ArrayList<>(); report.put("checks", checks); report.put("passed", false);
        StringBuffer output = new StringBuffer();
        List<ProcessHandler> owned = new ArrayList<>();
        XDebugSession debug = null;
        try {
            Files.writeString(evidence.resolve("startup.txt"), project.getBasePath());
            ui(() -> {
                var settings = SpellSettings.get(project).getState();
                settings.interpreter = System.getProperty("openbexi.interpreter");
                if (System.getProperty("openbexi.image") != null) settings.image = System.getProperty("openbexi.image");
                var tool = ToolWindowManager.getInstance(project).getToolWindow("SPELL");
                require(tool != null, "SPELL tool window was not registered"); tool.show();
                // Keep this private qualification instance out of the user's way.
                var frame = WindowManager.getInstance().getFrame(project);
                if (frame != null) frame.setVisible(false);
                return null;
            });
            checks.add("Installed plugin settings and tool window in actual IDE");
            Path editorManifest = Path.of(project.getBasePath(), ".openbexi/editor/current/manifest.json");
            if (Files.isRegularFile(editorManifest)) {
                String fixtureImage = com.google.gson.JsonParser.parseString(Files.readString(editorManifest)).getAsJsonObject().get("image_id").getAsString();
                ui(() -> {
                    var settings = SpellSettings.get(project).getState(); String originalImage = settings.image; settings.image = fixtureImage;
                    var root = LocalFileSystem.getInstance().refreshAndFindFileByPath(editorManifest.getParent().toString().replace('\\', '/'));
                    require(root != null, "Editor fixture not visible in VFS"); root.refresh(false, true);
                    var libraries = new SpellEditorLibrary().getAdditionalProjectLibraries(project);
                    require(libraries.size() == 1 && libraries.iterator().next().getSourceRoots().contains(root), "Generated editor definitions not exposed as synthetic library");
                    for (var module : com.intellij.openapi.module.ModuleManager.getInstance(project).getModules())
                        for (var sourceRoot : com.intellij.openapi.roots.ModuleRootManager.getInstance(module).getSourceRoots())
                            require(!sourceRoot.equals(root), "Editor definitions unexpectedly changed module runtime source roots");
                    project.getMessageBus().syncPublisher(com.intellij.openapi.roots.AdditionalLibraryRootsListener.TOPIC).libraryRootsChanged("OpenBEXI SPELL", List.of(), List.of(root), "qualification");
                    settings.image = "different-image";
                    require(new SpellEditorLibrary().getAdditionalProjectLibraries(project).isEmpty(), "Mismatched editor definitions remained active");
                    settings.image = originalImage; return null;
                });
                checks.add("Generated editor library is image-scoped and leaves module runtime source roots unchanged");
            }
            VirtualFile run = source(project, "run.py", "from spell.lang.functions import Display, Notify\nfrom pathlib import Path\nNotify('Voltage', '28.0', 'SUCCESS')\nDisplay('JETBRAINS_NATIVE_RUN')\nPath('answer.txt').write_text('42')\n");
            ui(() -> {
                // A first-start What's New tab can arrive after source() returns.
                // Select the real procedure immediately before exercising the action.
                FileEditorManager.getInstance(project).openFile(run, true);
                var context = SimpleDataContext.getProjectContext(project);
                var action = ActionManager.getInstance().getAction("OpenBEXI.Spell.Run");
                var event = AnActionEvent.createFromDataContext("SPELL qualification", new Presentation(), context);
                action.update(event);
                require(event.getPresentation().isEnabled(), "Run disabled when editor selection exists outside editor focus");
                return null;
            });
            checks.add("Run action uses the selected editor when a tool window has focus");
            ProcessHandler handler = ui(() -> { var process = SpellLaunch.run(project, run); process.addProcessListener(collect(output)); return process; });
            owned.add(handler);
            waitFor(handler::isProcessTerminated, "Run did not finish");
            require(handler.getExitCode() == 0 && output.toString().contains("JETBRAINS_NATIVE_RUN"), "Native Run failed: " + output);
            checks.add("Native Run through IDE process handler and console");
            require(ui(() -> SpellWorkspace.get(project).selected().status.equalsIgnoreCase("Finished")), "Workspace result did not record native finish");
            if (System.getProperty("openbexi.image") != null) {
                require(ui(() -> !SpellWorkspace.get(project).selected().lines.isEmpty()), "No native code notifications reached table");
                require(ui(() -> SpellWorkspace.get(project).selected().lines.values().stream().anyMatch(row -> row.item.equals("Voltage") && row.result.equals("SUCCESS"))), "Native ITEM result missing");
                captureWorkspace(project, evidence.resolve("workspace-results.png"));
            }
            {
                String recordedId = ui(() -> SpellWorkspace.get(project).selected().serviceId);
                ui(() -> { WriteAction.run(() -> run.rename(HostQualification.class, "run-moved.py")); return null; });
                SpellWorkspace records = ui(() -> new SpellWorkspace(project));
                try {
                    waitFor(() -> { try { return ui(() -> records.sessions().stream().anyMatch(item -> item.serviceId.equals(recordedId)
                        && String.join("\n", item.shownSource()).contains("JETBRAINS_NATIVE_RUN"))); }
                        catch (Exception error) { throw new RuntimeException(error); } }, "Captured source was lost when the original file moved");
                    checks.add("Completed history restores captured source when the original file no longer exists");
                } finally {
                    ui(() -> { records.dispose(); WriteAction.run(() -> run.rename(HostQualification.class, "run.py")); return null; });
                }
            }
            if (Boolean.getBoolean("openbexi.uiOnly")) {
                VirtualFile preview = source(project, "workspace_preview.py", "from spell.lang.functions import Notify, Prompt, Display\nfrom spell.lang.constants import YES_NO\nNotify('Voltage', '28.0', 'SUCCESS')\nPrompt('Ready to execute?', Type=YES_NO)\nDisplay('Complete')\n");
                ProcessHandler previewProcess = ui(() -> SpellLaunch.run(project, preview)); owned.add(previewProcess);
                awaitPrompt(project, "Ready to execute?");
                captureWorkspace(project, evidence.resolve("workspace-prompt.png"));
                ui(() -> { SpellWorkspace.get(project).stop(SpellWorkspace.get(project).selected()); return null; });
                waitFor(previewProcess::isProcessTerminated, "Preview prompt did not stop");
                checks.add("Presentation-only review captures real native prompt and current line highlight");
                report.put("passed", true); return;
            }
            // Controlled event ordering verifies parent/child isolation independently of scheduler timing.
            ui(() -> {
                var model = SpellWorkspace.get(project); var sessionState = model.selected(); String originalStatus = sessionState.status;
                var eventMethod = SpellWorkspace.class.getDeclaredMethod("event", SpellWorkspace.Session.class, String.class, com.google.gson.JsonObject.class);
                eventMethod.setAccessible(true); sessionState.status = "Paused";
                var child = new com.google.gson.JsonObject(); child.addProperty("ProcId", "child#2"); child.addProperty("promptId", "test-child"); child.addProperty("Text", "Controlled child prompt");
                eventMethod.invoke(model, sessionState, "spell/prompt", child);
                eventMethod.invoke(model, sessionState, "stopped", new com.google.gson.JsonObject());
                require(sessionState.status.equals("Paused") && sessionState.prompt != null, "Child prompt changed paused parent status or parent pause hid the prompt");
                var finishedChild = new com.google.gson.JsonObject(); finishedChild.addProperty("ProcId", "child#2"); finishedChild.addProperty("ExecutorStatus", "FINISHED"); finishedChild.addProperty("rootProcedureId", sessionState.rootProcedureId);
                eventMethod.invoke(model, sessionState, "spell/status", finishedChild);
                require(sessionState.status.equals("Paused") && sessionState.prompt == null, "Child FINISHED overwrote parent or left stale child prompt");
                sessionState.status = originalStatus; model.select(sessionState); return null;
            });
            checks.add("Controlled child prompt/status ordering preserves paused parent and scopes invalidation");
            ui(() -> { SpellSettings.get(project).getState().arguments = "invalid JSON"; return null; });
            ProcessHandler rejected = ui(() -> { var process = SpellLaunch.run(project, run); process.addProcessListener(collect(output)); return process; }); owned.add(rejected);
            waitFor(rejected::isProcessTerminated, "Rejected launch did not stop");
            require(rejected.getExitCode() != 0 && ui(() -> SpellWorkspace.get(project).selected().status.equals("Failed")), "Rejected launch was incorrectly marked Finished");
            ui(() -> { SpellSettings.get(project).getState().arguments = "{}"; return null; });
            checks.add("Native launch rejection remains Failed despite successful relay disconnect");
            VirtualFile control = source(project, "control.py", "from spell.lang.functions import Display\nvalue = 21\nanswer = value + 2\nDisplay('JETBRAINS_DEBUG_' + str(answer))\nassert answer == 42\n");
            XLineBreakpoint<?> breakpoint = ui(() -> WriteAction.compute(() ->
                XDebuggerManager.getInstance(project).getBreakpointManager().addLineBreakpoint(
                    XBreakpointType.EXTENSION_POINT_NAME.findExtension(SpellBreakpointType.class), control.getUrl(), 2, new SpellBreakpointType.Properties())));
            debug = ui(() -> SpellLaunch.debug(project, control));
            XDebugSession session = debug;
            report.put("debug_handler_start_notified", session.getDebugProcess().getProcessHandler().isStartNotified());
            owned.add(session.getDebugProcess().getProcessHandler());
            session.getDebugProcess().getProcessHandler().addProcessListener(collect(output));
            CountDownLatch paused = new CountDownLatch(1), stopped = new CountDownLatch(1);
            ui(() -> { session.addSessionListener(new XDebugSessionListener() {
                @Override public void sessionPaused() { paused.countDown(); }
                @Override public void sessionStopped() { stopped.countDown(); }
            }); return null; });
            require(paused.await(45, TimeUnit.SECONDS), "Debugger never paused");
            require(ui(() -> session.getCurrentPosition().getLine()) == 2, "Wrong native source position");
            XValue value = variable(session, "value");
            require("21".equals(value.getModifier().getInitialValueEditorText()), "Wrong initial native variable");
            CompletableFuture<Void> edited = new CompletableFuture<>();
            ui(() -> {
                value.getModifier().setValue(XDebuggerUtil.getInstance().createExpression("40", null, null, EvaluationMode.EXPRESSION), new XValueModifier.XModificationCallback() {
                    @Override public void valueModified() { edited.complete(null); }
                    @Override public void errorOccurred(String message) { edited.completeExceptionally(new AssertionError(message)); }
                }); return null;
            });
            edited.get(15, TimeUnit.SECONDS);
            require("40".equals(variable(session, "value").getModifier().getInitialValueEditorText()), "Native variable edit did not persist");
            ui(() -> {
                var frame = WindowManager.getInstance().getFrame(project);
                if (frame != null) {
                    var content = frame.getRootPane();
                    var capture = new BufferedImage(Math.max(1, content.getWidth()), Math.max(1, content.getHeight()), BufferedImage.TYPE_INT_RGB);
                    var graphics = capture.createGraphics(); content.printAll(graphics); graphics.dispose();
                    ImageIO.write(capture, "png", evidence.resolve("debugger.png").toFile());
                }
                return null;
            });
            CountDownLatch stepped = new CountDownLatch(1);
            ui(() -> { session.addSessionListener(new XDebugSessionListener() {
                @Override public void sessionPaused() { stepped.countDown(); }
            }); session.stepInto(); return null; });
            require(stepped.await(30, TimeUnit.SECONDS), "Step never paused");
            require(ui(() -> session.getCurrentPosition().getLine()) == 3, "Wrong Step position");
            ui(() -> { WriteAction.run(() -> XDebuggerManager.getInstance(project).getBreakpointManager().removeBreakpoint(breakpoint)); session.resume(); return null; });
            require(stopped.await(45, TimeUnit.SECONDS), "Debug session did not stop");
            waitFor(() -> session.getDebugProcess().getProcessHandler().isProcessTerminated(), "Debug adapter was not reaped");
            require(output.toString().contains("JETBRAINS_DEBUG_42"), "Final debugger output missing: " + output);
            checks.add("XDebugger breakpoint, stack/source position, variable edit, Step, Continue and output");
            VirtualFile prompt = source(project, "prompt.py", "from spell.lang.functions import Prompt, Display\nfrom spell.lang.constants import YES_NO\nfrom spell.lang.modifiers import Type\nassert Prompt('JETBRAINS_PROMPT?', {Type:YES_NO}) is True\nDisplay('JETBRAINS_PROMPT_COMPLETE')\n");
            debug = ui(() -> SpellLaunch.debug(project, prompt));
            XDebugSession prompting = debug;
            ProcessHandler promptHandler = prompting.getDebugProcess().getProcessHandler();
            owned.add(promptHandler); promptHandler.addProcessListener(collect(output));
            waitFor(() -> output.toString().contains("Enter the native option index:"), "Native prompt did not reach IDE console");
            promptHandler.getProcessInput().write("0\n".getBytes(java.nio.charset.StandardCharsets.UTF_8));
            promptHandler.getProcessInput().flush();
            waitFor(promptHandler::isProcessTerminated, "Prompt session did not stop");
            require(output.toString().contains("JETBRAINS_PROMPT_COMPLETE"), "Prompt answer failed");
            checks.add("Native prompt and answer through IDE console input");
            VirtualFile richPrompt = source(project, "workspace_prompt.py", "from spell.lang.functions import Prompt, Display\nfrom spell.lang.constants import YES_NO, ALPHA, NUM, LIST\nassert Prompt('Ready to execute?', Type=YES_NO) is True\nassert Prompt('Operator name', Type=ALPHA) == 'Ada'\nassert Prompt('Target count', Type=NUM) == 42\nassert Prompt('Choose a mode', ['Safe', 'Nominal'], Type=LIST|ALPHA) == 'Nominal'\nDisplay('JETBRAINS_WORKSPACE_PROMPTS_COMPLETE')\n");
            ProcessHandler rich = ui(() -> { var process = SpellLaunch.run(project, richPrompt); process.addProcessListener(collect(output)); return process; });
            owned.add(rich);
            awaitPrompt(project, "Ready to execute?");
            captureWorkspace(project, evidence.resolve("workspace-prompt.png"));
            ui(() -> {
                var choices = components(workspace(project), JRadioButton.class);
                require(choices.size() == 2, "Yes/No did not render two choices"); choices.getFirst().doClick();
                button(project, "Reset"); require(choices.stream().noneMatch(JRadioButton::isSelected), "Reset did not clear selection");
                choices.getFirst().doClick(); button(project, "Commit"); return null;
            });
            awaitPrompt(project, "Operator name");
            captureWorkspace(project, evidence.resolve("workspace-text-prompt.png"));
            ui(() -> { components(workspace(project), JTextField.class).stream().filter(field -> "SPELL prompt answer".equals(field.getName())).findFirst().orElseThrow().setText("Ada"); button(project, "Commit"); return null; });
            awaitPrompt(project, "Target count");
            ui(() -> {
                components(workspace(project), JTextField.class).stream().filter(field -> "SPELL prompt answer".equals(field.getName())).findFirst().orElseThrow().setText("not a number"); button(project, "Commit");
                require(SpellWorkspace.get(project).selected().prompt != null && !SpellWorkspace.get(project).selected().answering, "Invalid numeric input was submitted"); return null;
            });
            ui(() -> { components(workspace(project), JTextField.class).stream().filter(field -> "SPELL prompt answer".equals(field.getName())).findFirst().orElseThrow().setText("42"); button(project, "Commit"); return null; });
            awaitPrompt(project, "Choose a mode");
            ui(() -> { components(workspace(project), JRadioButton.class).get(1).doClick(); button(project, "Commit"); return null; });
            waitFor(rich::isProcessTerminated, "Workspace prompt procedure did not finish");
            require(rich.getExitCode() == 0 && output.toString().contains("JETBRAINS_WORKSPACE_PROMPTS_COMPLETE"), "Workspace prompt answers failed: " + output);
            checks.add("Embedded Yes/No, text, numeric and list prompts: native scoped answers, Commit and Reset");
            VirtualFile restoredPrompt = source(project, "reconnect.py", "from spell.lang.functions import Notify, Prompt, Display\nfrom spell.lang.constants import YES_NO\nNotify('TEMP', '20', 'SUCCESS')\nassert Prompt('RECONNECT_NATIVE?', Type=YES_NO) is True\nDisplay('JETBRAINS_RECONNECT_COMPLETE')\n");
            ProcessHandler leaving = ui(() -> SpellLaunch.run(project, restoredPrompt)); owned.add(leaving);
            awaitPrompt(project, "RECONNECT_NATIVE?");
            String originalId = ui(() -> SpellWorkspace.get(project).selected().serviceId);
            itemInformation(project, 3);
            checks.add("Native item-information dialog loads Latest, History and Full persisted notifications");
            ui(() -> { leaving.detachProcess(); return null; });
            waitFor(leaving::isProcessTerminated, "Workspace detach did not finish");
            SpellWorkspace reopened = ui(() -> new SpellWorkspace(project));
            try {
                waitFor(() -> {
                    try { return ui(() -> reopened.sessions().stream().anyMatch(candidate -> candidate.serviceId.equals(originalId) && candidate.active() && candidate.controller.isBlank())); }
                    catch (Exception error) { throw new RuntimeException(error); }
                }, "Reconnected workspace did not restore the original live instance");
                ui(() -> {
                    var restoredSession = reopened.sessions().stream().filter(item -> item.serviceId.equals(originalId)).findFirst().orElseThrow();
                    require(!restoredSession.controlling, "Reconnect silently took control"); reopened.select(restoredSession); reopened.control("openbexi/claim"); return null;
                });
                waitFor(() -> { try { return ui(() -> reopened.selected().controlling); } catch (Exception error) { throw new RuntimeException(error); } }, "Explicit claim was not acknowledged");
                ui(() -> { var restoredSession = reopened.selected(); reopened.answer(restoredSession, restoredSession.prompt.get("promptId").getAsString(), "0"); return null; });
                waitFor(() -> { try { return ui(() -> !reopened.selected().active()); } catch (Exception error) { throw new RuntimeException(error); } }, "Reconnected native prompt did not complete");
                require(ui(() -> reopened.selected().output.toString().contains("JETBRAINS_RECONNECT_COMPLETE")), "Reconnected result missing");
                checks.add("Detached native instance restored with source/history, monitored, explicitly claimed and answered without restarting");
            } finally { ui(() -> { reopened.dispose(); return null; }); }
            VirtualFile loop = source(project, "stop.py", "import time\nfrom spell.lang.functions import Display\nDisplay('JETBRAINS_STOP_READY')\nwhile True:\n    time.sleep(0.02)\n");
            ProcessHandler looping = ui(() -> { var process = SpellLaunch.run(project, loop); process.addProcessListener(collect(output)); return process; });
            owned.add(looping);
            waitFor(() -> output.toString().contains("JETBRAINS_STOP_READY"), "Loop did not start");
            ui(() -> { looping.destroyProcess(); return null; });
            waitFor(looping::isProcessTerminated, "IDE Stop did not reap the native runner");
            checks.add("IDE Stop gracefully closes its owned native run");
            report.put("passed", true);
        } catch (Throwable error) {
            var trace = new java.io.StringWriter(); error.printStackTrace(new java.io.PrintWriter(trace)); report.put("error", trace.toString());
        } finally {
            if (debug != null) {
                XDebugSession session = debug;
                try { ui(() -> { session.stop(); return null; }); } catch (Exception ignored) {}
            }
            for (ProcessHandler process : owned) {
                if (!process.isProcessTerminated()) process.destroyProcess();
                process.waitFor(15000);
            }
            try {
                Files.writeString(evidence.resolve("console.txt"), output.toString());
                Files.writeString(evidence.resolve("result.json"), new GsonBuilder().setPrettyPrinting().create().toJson(report));
            } catch (Exception error) { error.printStackTrace(); }
            System.exit(Boolean.TRUE.equals(report.get("passed")) ? 0 : 1);
        }
    }
}
