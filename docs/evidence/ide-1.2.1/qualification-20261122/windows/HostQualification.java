// Separate test plugin. This class never ships in the candidate ZIP.
package org.openbexi.spell.qualification;

import com.google.gson.GsonBuilder;
import com.intellij.ide.plugins.PluginManagerCore;
import com.intellij.openapi.actionSystem.*;
import com.intellij.openapi.actionSystem.impl.SimpleDataContext;
import com.intellij.openapi.application.ApplicationManager;
import com.intellij.openapi.extensions.PluginId;
import com.intellij.openapi.project.Project;
import com.intellij.openapi.startup.StartupActivity;
import com.intellij.openapi.vfs.LocalFileSystem;
import com.intellij.openapi.wm.ToolWindowManager;
import org.openbexi.spell.*;
import java.awt.*;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;
import javax.swing.*;

public final class HostQualification implements StartupActivity.DumbAware {
    private static final AtomicBoolean claimed = new AtomicBoolean();
    @Override public void runActivity(Project project) {
        if (System.getProperty("openbexi.qualification") == null || !claimed.compareAndSet(false, true)) return;
        Thread.ofVirtual().start(() -> run(project));
    }
    private static <T> T ui(Callable<T> work) throws Exception {
        var future = new FutureTask<T>(work);
        ApplicationManager.getApplication().invokeLater(future);
        return future.get(15, TimeUnit.SECONDS);
    }
    private static <T> ArrayList<T> elements(Container root, Class<T> type) {
        var found = new ArrayList<T>();
        for (var child : root.getComponents()) {
            if (type.isInstance(child)) found.add(type.cast(child));
            if (child instanceof Container sub) found.addAll(elements(sub, type));
        }
        return found;
    }
    private static void run(Project project) {
        var result = new LinkedHashMap<String,Object>();
        var checks = new ArrayList<String>();
        result.put("passed",false); result.put("checks",checks);
        Path evidence = Path.of(System.getProperty("openbexi.qualification"));
        try {
            var plugin = PluginManagerCore.getPlugin(PluginId.getId("org.openbexi.spell"));
            if (plugin == null || !"0.8.0".equals(plugin.getVersion())) throw new AssertionError("Incorrect loaded plugin");
            result.put("plugin_version",plugin.getVersion());
            String subject = "observer";
            ui(() -> {
                SpellSettings.get(project).getState().interpreter = System.getProperty("openbexi.interpreter");
                var action = ActionManager.getInstance().getAction("OpenBEXI.Spell.Gateway");
                var context = SimpleDataContext.getProjectContext(project);
                if (action == null) throw new AssertionError("Published v0.8 gateway action missing");
                action.actionPerformed(AnActionEvent.createFromAnAction(action, null, "OpenBEXI qualification", context));
                return null;
            });
            var window = ToolWindowManager.getInstance(project).getToolWindow("SPELL Server");
            SpellGatewayWindow.View view = null;
            for (int i=0; i<100 && view==null; i++) {
                view = ui(() -> {
                    var content = window.getContentManager().getSelectedContent();
                    return content == null ? null : (SpellGatewayWindow.View)content.getComponent();
                });
                if (view==null) Thread.sleep(100);
            }
            if (view==null) throw new AssertionError("Server tool window did not open");
            var panel = view;
            ui(() -> { panel.connect(Path.of(System.getenv("OPENBEXI_TEST_GATEWAY_CONFIG"))); return null; });
            boolean connected = false;
            for (int i=0; i<200 && !connected; i++) {
                connected = ui(() -> elements(panel,JLabel.class).stream().anyMatch(label -> label.getText().startsWith("Connected as " + subject)));
                if (!connected) Thread.sleep(100);
            }
            if (!connected) throw new AssertionError("Registered host did not display the certificate identity");
            checks.add("Opened the published Tools menu action and connected its native JetBrains Swing workspace to the named observer certificate");
            ui(() -> {
                var actions = elements(panel,JButton.class);
                for (String name : new String[]{"Reserve","Start native","Run / Continue","Step","Pause","Abort","Close native"}) {
                    var button=actions.stream().filter(b -> name.equals(b.getText())).findFirst().orElseThrow();
                    if (button.isEnabled()) throw new AssertionError("Observer can select " + name);
                }
                var file = LocalFileSystem.getInstance().refreshAndFindFileByIoFile(Path.of(project.getBasePath(),"user_script.py").toFile());
                if (file==null) throw new AssertionError("Private Python project missing");
                for (boolean debug : new boolean[]{false,true}) {
                    try {
                        if (debug) SpellLaunch.debug(project,file); else SpellLaunch.run(project,file);
                        throw new AssertionError("Local SPELL fallback accepted");
                    } catch (com.intellij.execution.ExecutionException expected) {
                        if (!expected.getMessage().contains("Disconnect")) throw expected;
                    }
                }
                actions.stream().filter(b -> "Disconnect".equals(b.getText())).findFirst().orElseThrow().doClick();
                return null;
            });
            checks.add("Observer mutation buttons disabled and both public local SPELL Run and Debug reject while connected");
            result.put("passed",true);
        } catch (Throwable error) { result.put("error",error.toString()); }
        finally {
            try { Files.writeString(evidence.resolve("result.json"),new GsonBuilder().setPrettyPrinting().create().toJson(result)); }
            catch (Exception error) { error.printStackTrace(); }
            System.exit(Boolean.TRUE.equals(result.get("passed"))?0:1);
        }
    }
}
