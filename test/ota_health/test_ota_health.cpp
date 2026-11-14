#include "gh_ota_health.h"

#include <cassert>
#include <cstring>
#include <iostream>
#include <iterator>
#include <string>

static const char* parse(const std::string& body) {
    return ghOtaHealthResponseError(body.c_str(), body.size());
}

int main(int argc, char** argv) {
    const std::string resource =
        R"({"limit":60,"remaining":59,"reset":1794047544,"used":1})";
    std::string body = R"({"resources":{)";
    for (int i = 0; i < 30; ++i) {
        if (i) body += ",";
        body += "\"resource_" + std::to_string(i) + "\":" + resource;
    }
    body += R"(},"rate":)" + resource + "}";

    assert(body.size() > 512 && body.size() < 4096);
    StaticJsonDocument<512> oldDocument;
    assert(deserializeJson(oldDocument, body.c_str()) == DeserializationError::NoMemory);
    assert(parse(body) == nullptr);
    assert(parse(R"({"rate":{"limit":60}})") == nullptr);
    assert(std::strcmp(parse(""), "EmptyInput") == 0);
    assert(parse(R"({"rate":{"limit":60)") != nullptr);
    assert(std::strcmp(parse(R"({"message":"service unavailable"})"), "InvalidResponse") == 0);
    assert(std::strcmp(parse(R"({"rate":{"limit":"60"}})"), "InvalidResponse") == 0);
    assert(std::strcmp(parse("[]"), "InvalidResponse") == 0);
    assert(std::strcmp(parse(R"({"rate":{"limit":-1}})"), "InvalidResponse") == 0);
    if (argc == 2 && std::strcmp(argv[1], "--stdin") == 0) {
        const std::string response((std::istreambuf_iterator<char>(std::cin)),
                                   std::istreambuf_iterator<char>());
        assert(!response.empty() && response.size() <= 4096);
        assert(parse(response) == nullptr);
    } else {
        assert(argc == 1);
    }
    return 0;
}
