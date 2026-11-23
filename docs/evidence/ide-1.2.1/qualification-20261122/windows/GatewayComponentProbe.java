// Exercise the actual packaged Swing component on an installed JetBrains runtime.
// This small Project provides only the interpreter setting. It is not a running JetBrains IDE.
import com.google.gson.*;
import com.intellij.openapi.project.Project;
import org.openbexi.spell.SpellGatewayWindow;
import org.openbexi.spell.SpellSettings;
import java.awt.*;
import java.awt.image.BufferedImage;
import java.io.*;
import java.lang.reflect.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.*;
import javax.imageio.ImageIO;
import javax.swing.*;

public final class GatewayComponentProbe {
    private static final JsonObject result = new JsonObject();
    private static final JsonArray events = new JsonArray();
    private static Path output;
    private static String worker, execution;
    private static JFrame frame;
    private static final ArrayList<SpellGatewayWindow.View> views = new ArrayList<>();

    private static <T> T ui(Callable<T> task) throws Exception {
        var future = new FutureTask<T>(task);
        SwingUtilities.invokeAndWait(future); return future.get();
    }
    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
    private static void waitFor(Callable<Boolean> condition, String label, int seconds) throws Exception {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(seconds);
        do { if (condition.call()) return; Thread.sleep(150); } while (System.nanoTime() < deadline);
        throw new AssertionError("Timeout " + label + ". " + ui(() -> views.stream()
            .flatMap(v -> items(v,JLabel.class).stream()).map(JLabel::getText).toList()));
    }
    private static <T> ArrayList<T> items(Container root, Class<T> type) {
        var all = new ArrayList<T>();
        for (var child : root.getComponents()) {
            if (type.isInstance(child)) all.add(type.cast(child));
            if (child instanceof Container nested) all.addAll(items(nested,type));
        }
        return all;
    }
    private static JButton button(SpellGatewayWindow.View view,String text) {
        return items(view,JButton.class).stream().filter(b -> text.equals(b.getText())).findFirst().orElseThrow();
    }
    private static void click(SpellGatewayWindow.View view, String text) throws Exception {
        ui(() -> { var button=button(view,text); require(button.isShowing() && button.isEnabled(),text+" unavailable"); button.doClick(); return null; });
    }
    private static void emit(String name, JsonObject data) throws IOException {
        data.addProperty("event",name); data.addProperty("at",Instant.now().toString());
        events.add(data);
        Files.writeString(output.resolve("events.jsonl"),data+"\n",StandardOpenOption.CREATE,StandardOpenOption.APPEND);
        System.out.println(name); System.out.flush();
    }
    private static SpellGatewayWindow.View create(String interpreter) throws Exception {
        var settings = new SpellSettings();
        settings.getState().interpreter=interpreter;
        Project stub=(Project)Proxy.newProxyInstance(Project.class.getClassLoader(),new Class<?>[]{Project.class},
            (target, method, args) -> {
                if (method.getName().equals("getService") && args[0]==SpellSettings.class) return settings;
                if (method.getName().equals("putUserData")) return null;
                throw new UnsupportedOperationException(method.toString());
            });
        var constructor=SpellGatewayWindow.View.class.getDeclaredConstructor(Project.class);
        constructor.setAccessible(true);
        return constructor.newInstance(stub);
    }
    private static void connect(SpellGatewayWindow.View panel,Path config,String role) throws Exception {
        ui(() -> { panel.connect(config); return null; });
        waitFor(() -> ui(() -> items(panel,JLabel.class).stream().anyMatch(l -> l.getText().startsWith("Connected as "+role))),
            "authenticating "+role,25);
    }
    private static JTable table(SpellGatewayWindow.View view) { return items(view,JTable.class).getFirst(); }
    private static String cell(SpellGatewayWindow.View view,String heading) {
        var grid=table(view);
        int column=grid.getColumnModel().getColumnIndex(heading);
        return grid.getRowCount()!=1 ? "" : String.valueOf(grid.getValueAt(0,column));
    }
    private static JsonObject workerEvent(String name) throws Exception {
        var proc=new ProcessBuilder("docker","logs",worker).redirectErrorStream(true).start();
        String data=new String(proc.getInputStream().readAllBytes(),StandardCharsets.UTF_8);
        require(proc.waitFor(5,TimeUnit.SECONDS) && proc.exitValue()==0,"Cannot inspect the assigned qualification worker");
        for (String line : data.lines().toList()) {
            if (!line.startsWith("{")) continue;
            var row=JsonParser.parseString(line).getAsJsonObject();
            if (row.has("event") && row.get("event").getAsString().equals(name)
                && row.has("execution_id") && row.get("execution_id").getAsString().equals(execution)) return row;
        }
        return null;
    }
    private static void refreshUntil(SpellGatewayWindow.View view,Callable<Boolean> condition,String label) throws Exception {
        waitFor(() -> {
            if (ui(condition)) return true;
            if (ui(() -> button(view,"Refresh").isEnabled())) click(view,"Refresh");
            Thread.sleep(450); return false;
        },label,35);
    }
    private static void capture(SpellGatewayWindow.View view,String name) throws Exception {
        ui(() -> { var image=new BufferedImage(view.getWidth(),view.getHeight(),BufferedImage.TYPE_INT_RGB);
            var graphics=image.createGraphics(); try { view.printAll(graphics); } finally { graphics.dispose(); }
            require(ImageIO.write(image,"png",output.resolve(name+".png").toFile()),"Screenshot failed"); return null; });
    }
    public static void main(String[] args) throws Exception {
        String interpreter=args[0];
        Path fixture=Path.of(args[1]);
        worker=args[2]; output=Path.of(args[3]); Files.createDirectory(output);
        result.addProperty("passed",false); result.add("events",events);
        result.addProperty("scope","Packaged native Swing components on the JetBrains SDK runtime. The two Project test objects provide only interpreter settings.");
        try {
            ui(() -> {
                frame=new JFrame("OpenBEXI packaged JetBrains component qualification");
                frame.setLayout(new GridLayout(2,1));
                for (int i=0;i<2;i++) { var panel=create(interpreter);views.add(panel);frame.add(panel); }
                frame.setSize(1150,700);frame.setVisible(true); return null;
            });
            var alice=views.get(0); var observer=views.get(1);
            connect(alice,fixture.resolve("alice/connection.json"),"alice");
            connect(observer,fixture.resolve("observer/connection.json"),"observer");
            require(ui(() -> !button(observer,"Reserve").isEnabled() && !button(observer,"Start native").isEnabled()),"Observer can mutate");
            var setup=JsonParser.parseString(Files.readString(fixture.resolve("case.json"))).getAsJsonObject();
            String revision=setup.get("revision").getAsString();
            require(ui(() -> items(alice,JLabel.class).stream().anyMatch(l -> l.getText().endsWith(" @ "+revision))),"Incorrect immutable source revision");
            emit("authenticated_roles",new JsonObject());
            click(alice,"Reserve");
            waitFor(() -> ui(() -> "RESERVED".equals(cell(alice,"Lifecycle")) && button(alice,"Start native").isEnabled()),"reserving",25);
            execution=ui(() -> cell(alice,"Execution")); require(UUID.fromString(execution).toString().equals(execution),"Invalid execution");
            result.addProperty("execution_id",execution); result.addProperty("source_revision",revision);
            capture(alice,"reserved"); click(alice,"Start native"); emit("start_native_clicked",new JsonObject());
            waitFor(() -> workerEvent("native-ready")!=null,"observing native-ready",75);
            var ready=workerEvent("native-ready"); require("PAUSED".equals(ready.get("native_status").getAsString()),"Native parent did not pause");
            emit("native_ready",ready); refreshUntil(alice,() -> button(alice,"Run / Continue").isEnabled(),"enabling Run");
            click(alice,"Run / Continue"); emit("run_continue_clicked",new JsonObject());
            waitFor(() -> workerEvent("native-finished")!=null,"native completion",80);
            var finished=workerEvent("native-finished");
            require("FINISHED".equals(finished.get("native_status").getAsString()) && finished.get("native_lifecycle_receipts_settled").getAsBoolean(),"Native completion unproven");
            emit("native_finished",finished);
            for (var view:views) {
                refreshUntil(view,() -> "FINISHED".equals(cell(view,"Native result")),"public native result");
                ui(() -> {table(view).setRowSelectionInterval(0,0);return null;});
                require(ui(() -> execution.equals(cell(view,"Execution")) && !button(view,"Run / Continue").isEnabled()
                    && !button(view,"Start native").isEnabled() && !button(view,"Step").isEnabled()),"Terminal controls or identity mismatch");
                String role=view==alice?"owner":"observer"; capture(view,role+"-finished");
                var report=new JsonObject();report.addProperty("role",role);report.addProperty("native_result","FINISHED");
                report.addProperty("lifecycle",ui(() -> cell(view,"Lifecycle")));emit("displayed_result",report);
            }
            for (var view:views) click(view,"Disconnect");
            waitFor(() -> ui(() -> views.stream().allMatch(v -> button(v,"Connect").isEnabled())),"disconnecting",20);
            result.addProperty("passed",true);
        } catch(Throwable error) { result.addProperty("error",error.toString()); error.printStackTrace(); }
        finally {
            Files.writeString(output.resolve("result.json"),new GsonBuilder().setPrettyPrinting().create().toJson(result));
            ui(() -> {for(var view:views)view.dispose();if(frame!=null)frame.dispose();return null;});
        }
        System.exit(result.get("passed").getAsBoolean()?0:1);
    }
}
