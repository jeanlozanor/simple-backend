import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:google_fonts/google_fonts.dart';
import 'package:url_launcher/url_launcher.dart';

/// Cambia esto si tu backend está en otra IP/puerto
// const String apiBaseUrl = 'http://10.0.2.2:8000'; // Android emulator -> host
// En dispositivo físico en la misma red:
// const String apiBaseUrl = 'http://10.221.163.2:8000';
// Backend en Render:
const String apiBaseUrl = 'https://simple-backend-fgyx.onrender.com';

/// Colores de marca SimPLE
const Color simpleBlue = Color(0xFF0077FF);
const Color simpleBlueDark = Color(0xFF0057C2);
const Color simpleYellow = Color(0xFFFFD600);

void main() {
  runApp(const SimpleApp());
}

class SimpleApp extends StatelessWidget {
  const SimpleApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'SimPLE',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: simpleBlue,
          primary: simpleBlue,
        ),
        scaffoldBackgroundColor: const Color(0xFFF3F6FC),
        useMaterial3: true,
        textTheme: GoogleFonts.manropeTextTheme(),
        appBarTheme: const AppBarTheme(
          elevation: 0,
          backgroundColor: Colors.transparent,
          foregroundColor: Colors.white,
        ),
      ),
      home: const ChatPage(),
    );
  }
}

/// Modelo de producto devuelto por tu backend
class Product {
  final String name;
  final String brand;
  final double price;
  final String currency;
  final String storeName;
  final String productUrl;
  final String? imageUrl;

  Product({
    required this.name,
    required this.brand,
    required this.price,
    required this.currency,
    required this.storeName,
    required this.productUrl,
    this.imageUrl,
  });

  factory Product.fromJson(Map<String, dynamic> json) {
    return Product(
      name: (json['name'] ?? '') as String,
      brand: (json['brand'] ?? '') as String,
      price: (json['price'] ?? 0).toDouble(),
      currency: (json['currency'] ?? 'PEN') as String,
      storeName: (json['store_name'] ?? '') as String,
      productUrl: (json['product_url'] ?? '') as String,
      imageUrl: json['image_url'] as String?,
    );
  }
}

enum MessageRole { user, assistant }

class ChatMessage {
  final MessageRole role;
  final String text;

  ChatMessage({required this.role, required this.text});
}

class ChatPage extends StatefulWidget {
  const ChatPage({super.key});

  @override
  State<ChatPage> createState() => _ChatPageState();
}

class _ChatPageState extends State<ChatPage> {
  final List<ChatMessage> _messages = [];
  final List<Product> _products = [];
  final TextEditingController _inputController = TextEditingController();
  final ScrollController _chatScrollController = ScrollController();
  bool _isLoading = false;

  @override
  void initState() {
    super.initState();
    _addWelcomeMessage();
  }

  void _addWelcomeMessage() {
    _messages.add(
      ChatMessage(
        role: MessageRole.assistant,
        text:
            'Hola, soy SimPLE 🤖🛒\n\n'
            'Cuéntame qué quieres comprar y tu presupuesto. Ejemplos:\n'
            '• "celular redmi buena batería entre 400 y 800 soles"\n'
            '• "audífonos bluetooth para caminar hasta 200 soles"\n\n'
            'Yo busco en las tiendas conectadas y te explico las opciones.',
      ),
    );
  }

  Future<void> _sendMessage() async {
    final text = _inputController.text.trim();
    if (text.isEmpty || _isLoading) return;

    setState(() {
      _messages.add(ChatMessage(role: MessageRole.user, text: text));
      _inputController.clear();
      _isLoading = true;
    });

    _scrollToBottom();

    try {
      final uri = Uri.parse(
        '$apiBaseUrl/chat?question=${Uri.encodeQueryComponent(text)}',
      );

      final response = await http.get(uri).timeout(
        const Duration(seconds: 120),
        onTimeout: () {
          throw Exception('Timeout: El servidor tardó demasiado en responder');
        },
      );

      if (response.statusCode != 200) {
        throw Exception('Error HTTP ${response.statusCode}: ${response.body}');
      }

      final Map<String, dynamic> data = json.decode(response.body);
      final String answer =
          (data['answer'] ?? 'No pude generar una respuesta.') as String;

      final List<dynamic> productsJson = data['products'] as List<dynamic>? ?? [];
      final List<Product> products =
          productsJson.map((p) => Product.fromJson(p as Map<String, dynamic>)).toList();

      setState(() {
        _messages.add(ChatMessage(role: MessageRole.assistant, text: answer));
        _products
          ..clear()
          ..addAll(products);
      });

      _scrollToBottom();
    } catch (e) {
      String errorMessage = 'Ups, hubo un problema al conectarme con el servidor de SimPLE.\n'
          'Revisa que el backend FastAPI esté corriendo y vuelve a intentarlo.\n\n'
          'Dirección configurada: $apiBaseUrl\n'
          'Detalle técnico: $e';

      setState(() {
        _messages.add(
          ChatMessage(
            role: MessageRole.assistant,
            text: errorMessage,
          ),
        );
      });
      _scrollToBottom();
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_chatScrollController.hasClients) {
        _chatScrollController.animateTo(
          _chatScrollController.position.maxScrollExtent + 80,
          duration: const Duration(milliseconds: 250),
          curve: Curves.easeOut,
        );
      }
    });
  }

  @override
  void dispose() {
    _inputController.dispose();
    _chatScrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        titleSpacing: 0,
        flexibleSpace: Container(
          decoration: const BoxDecoration(
            gradient: LinearGradient(
              colors: [simpleBlue, simpleBlueDark],
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
            ),
          ),
        ),
        title: Row(
          children: [
            Container(
              margin: const EdgeInsets.only(left: 12, right: 10),
              width: 34,
              height: 34,
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(10),
              ),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(10),
                child: Image.asset(
                  'assets/logo_simple.jpg',
                  fit: BoxFit.cover,
                ),
              ),
            ),
            Flexible(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'SimPLE',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: GoogleFonts.manrope(
                      fontSize: 18,
                      fontWeight: FontWeight.w800,
                      color: Colors.white,
                    ),
                  ),
                  Text(
                    'Tu asistente de compras',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: GoogleFonts.manrope(
                      fontSize: 11.5,
                      fontWeight: FontWeight.w500,
                      color: const Color(0xFFE8EEFF),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 12),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              decoration: BoxDecoration(
                color: Colors.white.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(999),
              ),
              child: Row(
                children: [
                  const Icon(Icons.store_mall_directory_rounded, size: 16, color: Colors.white),
                  const SizedBox(width: 6),
                  ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 190),
                    child: Text(
                      'Hiraoka · Falabella · Oechsle · PlazaVea',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: GoogleFonts.manrope(
                        fontSize: 11,
                        fontWeight: FontWeight.w600,
                        color: Colors.white,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          )
        ],
      ),
      body: SafeArea(
        child: Column(
          children: [
            // Chat
            Expanded(
              flex: 3,
              child: Container(
                margin: const EdgeInsets.all(12),
                padding: const EdgeInsets.fromLTRB(10, 10, 10, 8),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(color: const Color(0xFFE1E6F2)),
                  boxShadow: const [
                    BoxShadow(
                      color: Color(0x140F172A),
                      blurRadius: 14,
                      offset: Offset(0, 4),
                    ),
                  ],
                ),
                child: Column(
                  children: [
                    Expanded(
                      child: ListView.builder(
                        controller: _chatScrollController,
                        itemCount: _messages.length,
                        itemBuilder: (context, index) {
                          final msg = _messages[index];
                          final isUser = msg.role == MessageRole.user;
                          return Align(
                            alignment: isUser
                                ? Alignment.centerRight
                                : Alignment.centerLeft,
                            child: Container(
                              margin: const EdgeInsets.symmetric(
                                  vertical: 4, horizontal: 4),
                              padding: const EdgeInsets.symmetric(
                                  vertical: 10, horizontal: 12),
                              constraints: BoxConstraints(
                                maxWidth:
                                    MediaQuery.of(context).size.width * 0.8,
                              ),
                              decoration: BoxDecoration(
                                color: isUser
                                    ? simpleBlue
                                    : const Color(0xFFF2F6FF),
                                borderRadius: BorderRadius.only(
                                  topLeft: const Radius.circular(14),
                                  topRight: const Radius.circular(14),
                                  bottomLeft: isUser
                                      ? const Radius.circular(14)
                                      : const Radius.circular(6),
                                  bottomRight: isUser
                                      ? const Radius.circular(6)
                                      : const Radius.circular(14),
                                ),
                                border: isUser
                                    ? null
                                    : Border.all(
                                        color: const Color(0xFFCFDAF5),
                                      ),
                              ),
                              child: Text(
                                msg.text,
                                style: GoogleFonts.manrope(
                                  color: isUser
                                      ? Colors.white
                                      : const Color(0xFF0F172A),
                                  fontSize: 13.5,
                                  height: 1.35,
                                  fontWeight: FontWeight.w500,
                                ),
                              ),
                            ),
                          );
                        },
                      ),
                    ),
                    const SizedBox(height: 6),
                    // Input
                    _buildInputBar(),
                  ],
                ),
              ),
            ),

            // Productos
            Expanded(
              flex: 2,
              child: Container(
                width: double.infinity,
                margin: const EdgeInsets.fromLTRB(12, 0, 12, 12),
                padding: const EdgeInsets.fromLTRB(12, 10, 12, 12),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(18),
                  border: Border.all(color: const Color(0xFFE5E7EB)),
                  boxShadow: const [
                    BoxShadow(
                      color: Color(0x140F172A),
                      blurRadius: 14,
                      offset: Offset(0, 4),
                    ),
                  ],
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Row(
                            children: [
                              Container(
                                width: 6,
                                height: 18,
                                decoration: BoxDecoration(
                                  borderRadius: BorderRadius.circular(999),
                                  gradient: const LinearGradient(
                                    colors: [simpleYellow, simpleBlue],
                                    begin: Alignment.topCenter,
                                    end: Alignment.bottomCenter,
                                  ),
                                ),
                              ),
                              const SizedBox(width: 6),
                              Flexible(
                                child: Text(
                                  'Resultados recomendados',
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: GoogleFonts.manrope(
                                    fontSize: 13.5,
                                    fontWeight: FontWeight.w700,
                                    color: const Color(0xFF0F172A),
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(width: 8),
                        Flexible(
                          child: Container(
                            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                            decoration: BoxDecoration(
                              color: const Color(0xFFEEF2FF),
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: Text(
                              'Tiendas: Hiraoka · Falabella · Oechsle · PlazaVea',
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: GoogleFonts.manrope(
                                fontSize: 10.5,
                                fontWeight: FontWeight.w600,
                                color: const Color(0xFF1D4ED8),
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Expanded(
                      child: _products.isEmpty
                          ? Center(
                              child: Column(
                                mainAxisAlignment: MainAxisAlignment.center,
                                children: [
                                  Container(
                                    width: 54,
                                    height: 54,
                                    decoration: BoxDecoration(
                                      shape: BoxShape.circle,
                                      color: const Color(0xFFEEF2FF),
                                      border: Border.all(color: const Color(0xFFD9E3FF)),
                                    ),
                                    child: const Icon(
                                      Icons.shopping_bag_outlined,
                                      color: Color(0xFF1D4ED8),
                                      size: 28,
                                    ),
                                  ),
                                  const SizedBox(height: 10),
                                  Text(
                                    'Aquí verás los productos de Hiraoka, Falabella, Oechsle y PlazaVea.',
                                    textAlign: TextAlign.center,
                                    style: GoogleFonts.manrope(
                                      fontSize: 12,
                                      color: const Color(0xFF6B7280),
                                      height: 1.3,
                                    ),
                                  ),
                                ],
                              ),
                            )
                          : ListView.builder(
                              scrollDirection: Axis.horizontal,
                              itemCount: _products.length,
                              itemBuilder: (context, index) {
                                final product = _products[index];
                                return _ProductCard(product: product);
                              },
                            ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildInputBar() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
      decoration: BoxDecoration(
        color: const Color(0xFFF9FAFB),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: const Color(0xFFE5E7EB)),
      ),
      child: Row(
        children: [
          Expanded(
            child: TextField(
              controller: _inputController,
              enabled: !_isLoading,
              decoration: const InputDecoration(
                hintText:
                    'Ej: celular redmi buena batería entre 400 y 800 soles',
                border: InputBorder.none,
              ),
              style: GoogleFonts.manrope(fontSize: 13),
              onSubmitted: (_) => _sendMessage(),
            ),
          ),
          const SizedBox(width: 4),
          InkWell(
            onTap: _isLoading ? null : _sendMessage,
            borderRadius: BorderRadius.circular(999),
            child: Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: simpleYellow,
                borderRadius: BorderRadius.circular(999),
              ),
              child: _isLoading
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        valueColor:
                            AlwaysStoppedAnimation<Color>(simpleBlueDark),
                      ),
                    )
                  : const Icon(
                      Icons.send_rounded,
                      size: 18,
                      color: simpleBlueDark,
                    ),
            ),
          ),
        ],
      ),
    );
  }
}

/// Card de producto
class _ProductCard extends StatelessWidget {
  final Product product;

  const _ProductCard({required this.product});

  Future<void> _openProductUrl(BuildContext context) async {
    final url = product.productUrl.trim();
    if (url.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Este producto no tiene enlace.')),
      );
      return;
    }

    final uri = Uri.tryParse(url);
    if (uri == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Enlace inválido.')),
      );
      return;
    }

    final ok = await launchUrl(uri, mode: LaunchMode.externalApplication);
    if (!ok && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('No se pudo abrir el enlace.')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: () => _openProductUrl(context),
        borderRadius: BorderRadius.circular(12),
        child: Container(
          width: 180,
          margin: const EdgeInsets.only(right: 8),
          padding: const EdgeInsets.all(8),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: const Color(0xFFE5E7EB)),
            boxShadow: const [
              BoxShadow(
                color: Color(0x110F172A),
                blurRadius: 8,
                offset: Offset(0, 3),
              ),
            ],
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Imagen
              Expanded(
                child: Container(
                  width: double.infinity,
                  decoration: BoxDecoration(
                    color: const Color(0xFFF3F4F6),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: product.imageUrl != null
                      ? ClipRRect(
                          borderRadius: BorderRadius.circular(10),
                          child: Image.network(
                            product.imageUrl!,
                            fit: BoxFit.contain,
                            errorBuilder: (_, __, ___) =>
                                const Center(child: Text('Sin imagen')),
                          ),
                        )
                      : const Center(
                          child: Text(
                            'Sin imagen',
                            style: TextStyle(
                              fontSize: 11,
                              color: Color(0xFF9CA3AF),
                            ),
                          ),
                        ),
                ),
              ),
              const SizedBox(height: 6),
              Text(
                product.name,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(height: 2),
              Text(
                product.storeName,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  fontSize: 11,
                  color: Color(0xFF6B7280),
                ),
              ),
              const SizedBox(height: 4),
              Text(
                '${product.currency == 'PEN' ? 'S/ ' : ''}${product.price.toStringAsFixed(2)}',
                style: const TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.bold,
                  color: simpleBlueDark,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
